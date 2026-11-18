"""Track 3 Path Finder: 6-DoF trajectory from a degraded IMU recording.

    python src/main.py <imu csv | folder | zip> [estimated_trajectory.txt]

Input is EuRoC imu0/data.csv (timestamp ns, gyro rad/s, accel m/s^2). Output is
TUM format, one pose per input row, timestamps copied exactly from the input.

Pipeline
    1. read      stream the CSV into compact float32 arrays
    2. clean     drop duplicate, stuck and spiked rows, find the dead ending
    3. resample  valid rows onto a uniform grid, gaps bridged by interpolation
    4. attitude  integrate the gyro at full rate, then pull the tilt back to
                 gravity offline using a long average of world acceleration
    5. position  world acceleration averaged down to 20 Hz, double-integrated
                 in the frequency domain inside a band-pass, so slow drift from
                 bias and tilt error never builds up
    6. blind     after the sensor dies, coast on the last velocity and slow down
    7. write     interpolate poses onto every input timestamp, chunk by chunk

Memory stays small because nothing is held per input row except the timestamps
and the raw readings, and the position work runs at 20 Hz.
"""

import io
import math
import os
import sys
from array import array

import numpy as np

G = 9.80665
CHUNK = 4096
OUT_CHUNK = 1024

# tuned on the practice recordings, see README
CFG = {
    "calib_s": 1.5,        # start window for gyro bias and initial tilt
    "tilt_window_s": 30.0, # averaging window for the gravity direction
    "band_lo_hz": 0.02,    # position keeps motion above this frequency ...
    "band_hi_hz": 0.04,    # ... fully above this one, with a smooth ramp between
    "lp_hz": 3.0,          # above this, acceleration is vibration
    "gain": 0.25,          # horizontal shrink below split_hz: a too-large path costs more than a small one
    "gain_hi": 0.9,        # horizontal shrink above split_hz
    "split_hz": 0.08,
    "z_gain": 0.3,         # vertical shrink
    "z_band_lo_hz": 0.02,  # vertical pass band starts here
    "coast_tau_s": 0.6,    # blind segment: velocity decays with this time constant
    "return_tau_s": 0.25,  # blind segment: drift back to the path centre with this one
    "pos_hz": 20.0,        # rate of the position work
    "long_gap_s": 0.3,     # a dropout longer than this splits the attitude fix
    "gyro_noise_ref": 0.35,  # rad/s of sample-to-sample gyro jitter where trust halves
}


# ---------------------------------------------------------------- 1. read

def open_input(path):
    """Accepts the csv itself, a folder holding imu0/data.csv, or a zip of that folder."""
    if os.path.isdir(path):
        for cand in ("imu0/data.csv", "data.csv"):
            p = os.path.join(path, cand)
            if os.path.exists(p):
                return open(p, "r", encoding="utf-8-sig")
        raise SystemExit(f"no imu0/data.csv under {path}")
    if path.lower().endswith(".zip"):
        import zipfile  # costs about 0.9 MB, so only when a zip is given
        z = zipfile.ZipFile(path)
        names = [n for n in z.namelist() if n.endswith("imu0/data.csv")] or \
                [n for n in z.namelist() if n.endswith(".csv")]
        if not names:
            raise SystemExit(f"no csv inside {path}")
        return io.TextIOWrapper(z.open(names[0]), encoding="utf-8-sig")
    return open(path, "r", encoding="utf-8-sig")


def read_imu(path):
    ts = array("q")
    vals = array("f")
    with open_input(path) as f:
        for line in f:
            if not line or line[0] == "#":
                continue
            c = line.split(",")
            if len(c) < 7:
                continue
            try:
                t = int(c[0])
                row = (float(c[1]), float(c[2]), float(c[3]),
                       float(c[4]), float(c[5]), float(c[6]))
            except ValueError:
                try:  # a header without '#', or a float timestamp
                    t = int(float(c[0]))
                    row = tuple(float(v) for v in c[1:7])
                except ValueError:
                    continue
            ts.append(t)
            vals.extend(row)
    ts = np.frombuffer(ts, dtype=np.int64) if len(ts) else np.zeros(0, np.int64)
    imu = (np.frombuffer(vals, dtype=np.float32).reshape(-1, 6) if len(vals)
           else np.zeros((0, 6), np.float32))
    return ts, imu


# ---------------------------------------------------------------- 2. clean

def median(x):
    """np.median pulls in extra modules worth about 1.4 MB; partition does not."""
    x = np.asarray(x, dtype=np.float64).ravel()
    k = len(x) // 2
    return float(np.partition(x, k)[k])


def gyro_first(imu):
    """EuRoC order is gyro, accel. Swap if the first triple looks like gravity."""
    n = len(imu)
    if n < 3:
        return imu
    s = imu[::max(1, n // 2000)]
    s = s[np.any(s != 0, axis=1)]
    if len(s) < 3:
        return imu
    n1 = median(np.linalg.norm(s[:, 0:3], axis=1))
    n2 = median(np.linalg.norm(s[:, 3:6], axis=1))
    if n1 > 3.0 and n2 < 3.0:
        return np.ascontiguousarray(imu[:, [3, 4, 5, 0, 1, 2]])
    return imu


def clean(ts, imu):
    """Returns (valid mask, index of the first dead row)."""
    n = len(ts)
    valid = np.ones(n, bool)

    # dead ending: trailing rows where every value is exactly zero
    nonzero = np.any(imu != 0, axis=1)
    alive = np.flatnonzero(nonzero)
    dead_from = int(alive[-1]) + 1 if len(alive) else 0
    valid &= nonzero
    del nonzero, alive

    if n > 1:
        same = np.all(imu[1:] == imu[:-1], axis=1)       # duplicates and stuck repeats
        same |= ts[1:] <= ts[:-1]                         # repeated or backwards timestamps
        valid[1:] &= ~same
        del same

    # spikes: a sample far from the median of itself and its two neighbours,
    # measured against the local noise level
    idx = np.flatnonzero(valid)
    if len(idx) > 20:
        spike = np.zeros(len(idx), bool)
        w = 101
        for ch in range(6):
            x = imu[idx, ch].astype(np.float64)
            a = np.empty_like(x)
            c = np.empty_like(x)
            a[1:] = x[:-1]
            a[0] = x[1]
            c[:-1] = x[1:]
            c[-1] = x[-2]
            med = np.maximum(np.minimum(a, x), np.minimum(np.maximum(a, x), c))
            res = np.abs(x - med)
            del a, c, med, x
            cs = np.cumsum(np.pad(res, (w // 2 + 1, w // 2), mode="edge"))
            local = (cs[w:] - cs[:-w]) / w
            floor = 0.05 if ch < 3 else 0.5
            spike |= res > 8.0 * local + floor
            del cs, local, res
        valid[idx[spike]] = False
    return valid, dead_from


# ---------------------------------------------------------------- 3. resample

def resample(t, imu, valid, fs):
    tv = t[valid]
    m = int(math.floor((tv[-1] - tv[0]) * fs + 1e-9)) + 1
    grid0 = float(tv[0])
    out = np.empty((m, 6), np.float32)
    for ch in range(6):
        col = imu[valid, ch].astype(np.float64)
        for s in range(0, m, CHUNK):
            grid = grid0 + np.arange(s, min(s + CHUNK, m)) / fs
            out[s:s + len(grid), ch] = np.interp(grid, tv, col)
        del col
    # grid samples that fall inside a long gap carry no real measurement
    gap = np.zeros(m, bool)
    for k in np.flatnonzero(np.diff(tv) > CFG["long_gap_s"]):
        a = int(math.ceil((tv[k] - grid0) * fs))
        b = int(math.floor((tv[k + 1] - grid0) * fs))
        gap[max(a, 0):max(b + 1, 0)] = True
    return grid0, out, gap


# ---------------------------------------------------------------- 4. attitude

def qmul(a, b):
    ax, ay, az, aw = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bx, by, bz, bw = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz], axis=-1)


def qrot(q, v):
    """Rotate vectors v (N,3) by quaternions q (N,4), body to world."""
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    vx, vy, vz = v[:, 0], v[:, 1], v[:, 2]
    tx = 2 * (y * vz - z * vy)
    ty = 2 * (z * vx - x * vz)
    tz = 2 * (x * vy - y * vx)
    return np.stack([vx + w * tx + y * tz - z * ty,
                     vy + w * ty + z * tx - x * tz,
                     vz + w * tz + x * ty - y * tx], axis=1)


def arc_to_z(u):
    """Shortest rotations taking directions u (N,3) onto +z."""
    u = u / np.maximum(np.linalg.norm(u, axis=1, keepdims=True), 1e-12)
    s = np.sqrt(np.maximum(2.0 * (1.0 + u[:, 2]), 1e-12))
    return np.stack([u[:, 1] / s, -u[:, 0] / s, np.zeros(len(u)), s / 2], axis=1)


def smooth(x, n):
    """Centred moving average over n samples along axis 0, edges shrink the window."""
    m = len(x)
    if n <= 1 or m < 2:
        return x.copy()
    h = n // 2
    c = np.zeros((m + 1,) + x.shape[1:])
    np.cumsum(x, axis=0, out=c[1:])
    i = np.arange(m)
    lo = np.maximum(i - h, 0)
    hi = np.minimum(i + h + 1, m)
    return (c[hi] - c[lo]) / (hi - lo)[:, None]


def smooth_segments(x, n, seg, w):
    """Weighted centred moving average that never crosses a segment boundary."""
    out = np.empty_like(x)
    cuts = np.flatnonzero(np.diff(seg)) + 1
    for a, b in zip(np.concatenate([[0], cuts]), np.concatenate([cuts, [len(x)]])):
        ws = w[a:b, None]
        num = smooth(x[a:b] * ws, n)
        den = smooth(ws, n)
        out[a:b] = num / np.maximum(den, 1e-9)
        if not (den > 1e-9).any():
            out[a:b] = x[a:b]
    return out


def block_flags(gap, d):
    """Per block: inside a long gap, and segment number (a new one after each gap)."""
    nb = len(gap) // d
    bg = gap[:nb * d].reshape(nb, d).any(axis=1)
    seg = np.cumsum(np.concatenate([[False], bg[1:] & ~bg[:-1]]))
    return bg, seg


def gyro_quality(gyro, d):
    """1 where the gyro looks healthy, falling to 0 where it is mostly noise."""
    nb = len(gyro) // d
    if nb < 1:
        return np.ones(0)
    hf = np.empty(nb)
    step = max(CHUNK // d, 1) * d
    for s in range(0, nb * d, step):
        e = min(s + step, nb * d)
        x = gyro[max(s - 1, 0):e].astype(np.float64)
        dg = np.diff(x, axis=0)
        if s == 0:
            dg = np.concatenate([np.zeros((1, 3)), dg])
        hf[s // d:e // d] = np.sqrt((dg * dg).sum(axis=1).reshape(-1, d).mean(axis=1))
    hf = smooth(hf[:, None], max(int(5.0 * CFG["pos_hz"]), 1))[:, 0]
    return 1.0 / (1.0 + (hf / CFG["gyro_noise_ref"]) ** 4)


def integrate_gyro(gyro, q0, fs, bias):
    """Body-rate integration, sequential, so plain floats in small blocks."""
    n = len(gyro)
    q = np.empty((n, 4), np.float32)
    x, y, z, w = (float(v) for v in q0)
    h = 0.5 / fs
    bx, by, bz = (float(v) for v in bias)
    for start in range(0, n, 1024):
        block = gyro[start:start + 1024].tolist()
        rows = []
        for gx, gy, gz in block:
            rows.append((x, y, z, w))
            hx, hy, hz = (gx - bx) * h, (gy - by) * h, (gz - bz) * h
            x, y, z, w = (x + w * hx + y * hz - z * hy,
                          y + w * hy + z * hx - x * hz,
                          z + w * hz + x * hy - y * hx,
                          w - x * hx - y * hy - z * hz)
            r = 1.0 / math.sqrt(x * x + y * y + z * z + w * w)
            x *= r; y *= r; z *= r; w *= r
        q[start:start + len(rows)] = rows
    return q


def block_world_acc(q, acc, d):
    """World-frame acceleration averaged over blocks of d samples."""
    n = len(q)
    nb = n // d
    out = np.empty((nb, 3))
    step = max(CHUNK // d, 1) * d
    for s in range(0, nb * d, step):
        e = min(s + step, nb * d)
        aw = qrot(q[s:e].astype(np.float64), acc[s:e].astype(np.float64))
        out[s // d:e // d] = aw.reshape(-1, d, 3).mean(axis=1)
    return out


def apply_correction(q, corr, d):
    """Left-multiply q by correction quaternions given once per block, interpolated."""
    n = len(q)
    nb = len(corr)
    tb = (np.arange(nb) + 0.5) * d
    for s in range(0, n, CHUNK):
        e = min(s + CHUNK, n)
        ti = np.arange(s, e)
        c = np.stack([np.interp(ti, tb, corr[:, k]) for k in range(4)], axis=1)
        c /= np.linalg.norm(c, axis=1, keepdims=True)
        r = qmul(c, q[s:e].astype(np.float64))
        q[s:e] = r / np.linalg.norm(r, axis=1, keepdims=True)


def attitude(g, fs, d, calib_n, bgap, seg):
    head_g = g[:calib_n, 0:3].astype(np.float64)
    still = len(head_g) > 10 and np.linalg.norm(head_g.std(axis=0)) < 0.05
    bias = head_g.mean(axis=0) if still else np.zeros(3)
    q0 = arc_to_z(g[:max(calib_n, 1), 3:6].astype(np.float64).mean(axis=0, keepdims=True))[0]
    q = integrate_gyro(g[:, 0:3], q0, fs, bias)

    # offline tilt correction: averaged over tens of seconds, world acceleration
    # is gravity alone, so rotate each pose until that average points up
    if len(q) >= d:
        win = max(int(CFG["tilt_window_s"] * fs / d), 1)
        for _ in range(2):
            up = smooth_segments(block_world_acc(q, g[:, 3:6], d), win, seg, (~bgap).astype(float))
            apply_correction(q, arc_to_z(up), d)
    return q


# ---------------------------------------------------------------- 5. position

def band_integrate(a, fs):
    """Position from acceleration: divide by -(2 pi f)^2 inside a smooth pass band."""
    n = len(a)
    if n < 8:
        return np.zeros((n, 3))
    a = a - a.mean(axis=0)
    pad = n // 2
    taper = np.ones(n)
    m = min(int(2 * fs), n // 4)
    if m > 1:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, m))
        taper[:m] = ramp
        taper[-m:] = ramp[::-1]
    nfft = 1
    while nfft < n + 2 * pad:
        nfft *= 2
    f = np.fft.rfftfreq(nfft, 1.0 / fs)
    nz = f > 0
    base = np.zeros_like(f)
    base[nz] = -1.0 / (1.0 + (f[nz] / CFG["lp_hz"]) ** 8) / (2 * math.pi * f[nz]) ** 2

    def ramp(lo, hi):
        r = np.clip((f - lo) / max(hi - lo, 1e-9), 0, 1)
        return 0.5 - 0.5 * np.cos(math.pi * r)

    # horizontal: tilt error leaks g*sin(tilt) here, so trust slow motion less
    split = CFG["split_hz"]
    h_gain = base * ramp(CFG["band_lo_hz"], CFG["band_hi_hz"]) * (
        CFG["gain"] + (CFG["gain_hi"] - CFG["gain"]) * ramp(split / 1.5, split * 1.5))
    # vertical: tilt error only leaks g*(1-cos(tilt)), so a wider band holds up
    z_gain = base * ramp(CFG["z_band_lo_hz"], 2 * CFG["z_band_lo_hz"]) * CFG["z_gain"]

    p = np.empty((n, 3))
    buf = np.zeros(nfft)
    for ax in range(3):
        buf[:] = 0.0
        buf[pad:pad + n] = a[:, ax] * taper
        spec = np.fft.rfft(buf)
        spec *= z_gain if ax == 2 else h_gain
        p[:, ax] = np.fft.irfft(spec, nfft)[pad:pad + n]
    return p


# ---------------------------------------------------------------- 6+7. blind and write

def fmt_ts(t):
    return f"{t // 1000000000}.{t % 1000000000:09d}"


def write_identity(path, ts):
    with open(path, "w", newline="\n") as out:
        out.write("# timestamp tx ty tz qx qy qz qw\n")
        for s in range(0, len(ts), CHUNK):
            out.write("".join(f"{fmt_ts(t)} 0.000000 0.000000 0.000000 0 0 0 1\n"
                              for t in ts[s:s + CHUNK].tolist()))


def coast_state(model):
    p, pt = model["p"], model["pt"]
    m = max(int(0.5 * CFG["pos_hz"]), 2)
    if len(p) > m:
        return (p[-1] - p[-m]) / (pt[-1] - pt[-m])
    return np.zeros(3)


def poses(tc, model, v_end):
    """Position and orientation at times tc (seconds from the first row)."""
    grid0, fs, q, pt, p = model["grid0"], model["fs"], model["q"], model["pt"], model["p"]
    pos = np.stack([np.interp(tc, pt, p[:, k]) for k in range(3)], axis=1)
    fi = (tc - grid0) * fs
    idx = np.arange(len(q))
    quat = np.stack([np.interp(fi, idx, q[:, k]) for k in range(4)], axis=1)
    end = pt[-1]
    after = tc > end
    if after.any():
        dt = tc[after] - end
        tau = CFG["coast_tau_s"]
        k = tau * (1.0 - np.exp(-dt / tau)) if tau > 0 else np.zeros(len(dt))
        back = np.exp(-dt / CFG["return_tau_s"])[:, None]
        pos[after] = p[-1] * back + k[:, None] * v_end
        quat[after] = q[-1]
    quat /= np.linalg.norm(quat, axis=1, keepdims=True)
    return pos, quat


def write(path, ts, model):
    v_end = coast_state(model)
    with open(path, "w", newline="\n") as out:
        out.write("# timestamp tx ty tz qx qy qz qw\n")
        for s in range(0, len(ts), OUT_CHUNK):
            pos, quat = poses((ts[s:s + OUT_CHUNK] - ts[0]) * 1e-9, model, v_end)
            out.write("".join(
                f"{fmt_ts(a)} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} "
                f"{c[0]:.7f} {c[1]:.7f} {c[2]:.7f} {c[3]:.7f}\n"
                for a, b, c in zip(ts[s:s + OUT_CHUNK].tolist(), pos.tolist(), quat.tolist())))


# ---------------------------------------------------------------- main

def estimate(ts, imu):
    """Returns the model needed to write poses, or None when there is too little data.

    imu may be passed inside a one-item list, so that it can be released here
    once it has been resampled instead of living until the caller returns.
    """
    if isinstance(imu, list):
        imu = imu.pop()
    n = len(ts)
    if n == 0:
        return None
    imu = gyro_first(imu)
    valid, dead_from = clean(ts, imu)
    t = (ts - ts[0]) * 1e-9
    if valid.sum() < 10 or t[-1] <= 0:
        return None

    dts = np.diff(t[valid])
    dts = dts[dts > 0]
    fs = 1.0 / median(dts) if len(dts) else 200.0
    fs = min(max(fs, 20.0), 1000.0)

    grid0, g, gap = resample(t, imu, valid, fs)
    del valid, imu, t
    d = max(int(round(fs / CFG["pos_hz"])), 1)
    calib_n = max(int(CFG["calib_s"] * fs), 1)
    bgap, seg = block_flags(gap, d)
    del gap
    q = attitude(g, fs, d, calib_n, bgap, seg)

    if len(q) >= 2 * d:
        acc_w = block_world_acc(q, g[:, 3:6], d)
        cb = max(calib_n // d, 1)
        g_mag = float(np.linalg.norm(acc_w[:cb].mean(axis=0)))
        acc_w[:, 2] -= g_mag
        acc_w[bgap] = 0.0          # nothing was measured there
        p = band_integrate(acc_w, fs / d)
        p *= gyro_quality(g[:, 0:3], d)[:, None]
        pt = grid0 + (np.arange(len(p)) + 0.5) * d / fs
        del acc_w
    else:
        p = np.zeros((1, 3))
        pt = np.array([grid0])
    del g
    return {"grid0": grid0, "fs": fs, "q": q, "pt": pt, "p": p}


def main(argv):
    if len(argv) < 2:
        raise SystemExit("usage: python main.py <imu csv | folder | zip> [output txt]")
    src = argv[1]
    dst = argv[2] if len(argv) > 2 else "estimated_trajectory.txt"
    ts, imu = read_imu(src)
    box = [imu]
    del imu
    model = estimate(ts, box)
    if model is None:
        write_identity(dst, ts)
    else:
        write(dst, ts, model)


if __name__ == "__main__":
    main(sys.argv)
