"""Track 3 Path Finder: 6-DoF trajectory from a degraded IMU recording.

    python src/main.py <imu csv | folder | zip> [estimated_trajectory.txt]

Input is EuRoC imu0/data.csv (timestamp ns, gyro rad/s, accel m/s^2). Output is
TUM format, one pose per input row, timestamps copied exactly from the input.

Pipeline
    1. read      stream the CSV into compact arrays
    2. clean     drop duplicate, stuck and spiked rows, find the dead ending
    3. resample  valid rows onto a uniform grid, gaps bridged by interpolation
    4. attitude  integrate the gyro, then pull the tilt back to gravity offline
    5. position  double-integrate in the frequency domain with a band-pass,
                 so slow drift from bias and tilt error never builds up
    6. blind     after the sensor dies, coast on the last velocity and slow down
    7. write     map grid poses back onto every input timestamp
"""

import io
import math
import os
import sys
import zipfile
from array import array

import numpy as np

G = 9.80665

# tuned on the practice recordings, see README
CFG = {
    "calib_s": 1.5,        # start window for gyro bias and initial tilt
    "tilt_window_s": 6.0,  # averaging window for the gravity direction
    "band_lo_hz": 0.06,    # position keeps motion between these frequencies
    "band_hi_hz": 0.10,
    "lp_hz": 3.0,          # above this, acceleration is vibration
    "gain": 0.75,          # shrink, a too-large path costs more than a small one
    "coast_tau_s": 0.6,    # blind segment: velocity decays with this time constant
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
        z = zipfile.ZipFile(path)
        names = [n for n in z.namelist() if n.endswith("imu0/data.csv")] or \
                [n for n in z.namelist() if n.endswith(".csv")]
        if not names:
            raise SystemExit(f"no csv inside {path}")
        return io.TextIOWrapper(z.open(names[0]), encoding="utf-8-sig")
    return open(path, "r", encoding="utf-8-sig")


def read_imu(path):
    ts = array("q")
    vals = array("d")
    with open_input(path) as f:
        for line in f:
            if not line or line[0] == "#":
                continue
            c = line.split(",")
            if len(c) < 7:
                continue
            try:
                t = int(c[0])
                row = [float(c[1]), float(c[2]), float(c[3]),
                       float(c[4]), float(c[5]), float(c[6])]
            except ValueError:
                try:  # a header without '#', or a float timestamp
                    t = int(float(c[0]))
                    row = [float(v) for v in c[1:7]]
                except ValueError:
                    continue
            ts.append(t)
            vals.extend(row)
    ts = np.frombuffer(ts, dtype=np.int64) if len(ts) else np.zeros(0, np.int64)
    imu = np.frombuffer(vals, dtype=np.float64).reshape(-1, 6) if len(vals) else np.zeros((0, 6))
    return ts, imu


# ---------------------------------------------------------------- 2. clean

def gyro_first(imu):
    """EuRoC order is gyro, accel. Swap if the first triple looks like gravity."""
    if len(imu) < 3:
        return imu
    live = imu[np.any(imu != 0, axis=1)]
    if len(live) < 3:
        return imu
    n1 = np.median(np.linalg.norm(live[:, 0:3], axis=1))
    n2 = np.median(np.linalg.norm(live[:, 3:6], axis=1))
    if n1 > 3.0 and n2 < 3.0:
        return np.ascontiguousarray(imu[:, [3, 4, 5, 0, 1, 2]])
    return imu


def clean(ts, imu):
    """Returns (valid mask, index of the first dead row)."""
    n = len(ts)
    valid = np.ones(n, bool)

    # dead ending: trailing rows where every value is exactly zero
    alive = np.flatnonzero(np.any(imu != 0, axis=1))
    dead_from = int(alive[-1]) + 1 if len(alive) else 0
    valid[dead_from:] = False
    valid[np.all(imu == 0, axis=1)] = False

    if n > 1:
        same_val = np.all(imu[1:] == imu[:-1], axis=1)
        valid[1:][same_val] = False                      # duplicates and stuck repeats
        valid[1:][ts[1:] <= ts[:-1]] = False             # repeated or backwards timestamps

    # spikes: a sample far from the median of its neighbours, scaled by local noise
    idx = np.flatnonzero(valid)
    if len(idx) > 20:
        x = imu[idx]
        spike = np.zeros(len(idx), bool)
        for ch in range(6):
            col = x[:, ch]
            pad = np.pad(col, 2, mode="edge")
            win = np.stack([pad[k:k + len(col)] for k in range(5)], axis=1)
            res = np.abs(col - np.median(win, axis=1))
            del win, pad
            w = 101
            c = np.cumsum(np.pad(res, (w // 2, w // 2), mode="edge"))
            local = (c[w:] - c[:-w]) / w
            local = np.concatenate([local[:1], local])[:len(res)]
            floor = 0.05 if ch < 3 else 0.5
            spike |= res > 8.0 * local + floor
        valid[idx[spike]] = False
    return valid, dead_from


# ---------------------------------------------------------------- 3. resample

def resample(t, imu, valid, fs):
    tv = t[valid]
    grid = np.arange(tv[0], tv[-1] + 0.5 / fs, 1.0 / fs)
    out = np.empty((len(grid), 6))
    for ch in range(6):
        out[:, ch] = np.interp(grid, tv, imu[valid, ch])
    return grid, out


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
    if n <= 1 or len(x) < 2:
        return x.copy()
    h = n // 2
    c = np.cumsum(np.concatenate([np.zeros((1,) + x.shape[1:]), x]), axis=0)
    i = np.arange(len(x))
    lo = np.clip(i - h, 0, len(x))
    hi = np.clip(i + h + 1, 0, len(x))
    return (c[hi] - c[lo]) / (hi - lo)[:, None]


def attitude(gyro, acc, fs, calib_n):
    head_g = gyro[:calib_n]
    still = len(head_g) > 10 and np.linalg.norm(head_g.std(axis=0)) < 0.05
    bias = head_g.mean(axis=0) if still else np.zeros(3)

    n = len(gyro)
    q = np.empty((n, 4))
    q0 = arc_to_z(acc[:max(calib_n, 1)].mean(axis=0, keepdims=True))[0]
    x, y, z, w = (float(v) for v in q0)
    h = 0.5 / fs
    rates = ((gyro - bias) * h).tolist() if n < 4096 else None
    # gyro integration is sequential; plain floats in chunks keep it fast and small
    out = q
    for start in range(0, n, 4096):
        block = rates if rates is not None else ((gyro[start:start + 4096] - bias) * h).tolist()
        for k, (hx, hy, hz) in enumerate(block):
            i = start + k
            out[i, 0] = x
            out[i, 1] = y
            out[i, 2] = z
            out[i, 3] = w
            x, y, z, w = (x + w * hx + y * hz - z * hy,
                          y + w * hy + z * hx - x * hz,
                          z + w * hz + x * hy - y * hx,
                          w - x * hx - y * hy - z * hz)
            r = 1.0 / math.sqrt(x * x + y * y + z * z + w * w)
            x *= r; y *= r; z *= r; w *= r
        if rates is not None:
            break

    # offline tilt correction: averaged over a few seconds, world acceleration
    # is gravity alone, so rotate each pose until that average points up
    win = max(int(CFG["tilt_window_s"] * fs), 1)
    for _ in range(2):
        up = smooth(qrot(q, acc), win)
        q = qmul(arc_to_z(up), q)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
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
    lo, hi, lp = CFG["band_lo_hz"], CFG["band_hi_hz"], CFG["lp_hz"]
    hp = np.clip((f - lo) / max(hi - lo, 1e-9), 0, 1)
    hp = 0.5 - 0.5 * np.cos(math.pi * hp)
    lpw = 1.0 / (1.0 + (f / lp) ** 8)
    gain = np.zeros_like(f)
    nz = f > 0
    gain[nz] = -hp[nz] * lpw[nz] / (2 * math.pi * f[nz]) ** 2
    p = np.empty((n, 3))
    for ax in range(3):
        buf = np.zeros(nfft)
        buf[pad:pad + n] = a[:, ax] * taper
        spec = np.fft.rfft(buf)
        spec *= gain
        p[:, ax] = np.fft.irfft(spec, nfft)[pad:pad + n]
    return p * CFG["gain"]


# ---------------------------------------------------------------- 6. blind

def coast(p_end, v_end, tau_rel):
    tau = CFG["coast_tau_s"]
    k = tau * (1.0 - np.exp(-tau_rel / tau))
    return p_end[None, :] + k[:, None] * v_end[None, :]


# ---------------------------------------------------------------- 7. write

def write(path, ts, pos, quat):
    with open(path, "w", newline="\n") as out:
        out.write("# timestamp tx ty tz qx qy qz qw\n")
        step = 2000
        for s in range(0, len(ts), step):
            tsl = ts[s:s + step].tolist()
            pl = pos[s:s + step].tolist()
            ql = quat[s:s + step].tolist()
            out.write("".join(
                f"{t // 1000000000}.{t % 1000000000:09d} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} "
                f"{q[0]:.7f} {q[1]:.7f} {q[2]:.7f} {q[3]:.7f}\n"
                for t, p, q in zip(tsl, pl, ql)))


# ---------------------------------------------------------------- main

def estimate(ts, imu):
    n = len(ts)
    pos = np.zeros((n, 3))
    quat = np.zeros((n, 4))
    quat[:, 3] = 1.0
    if n == 0:
        return pos, quat

    imu = gyro_first(imu)
    valid, dead_from = clean(ts, imu)
    t = (ts - ts[0]) * 1e-9
    if valid.sum() < 10 or t[-1] <= 0:
        return pos, quat

    dts = np.diff(t[valid])
    dts = dts[dts > 0]
    fs = 1.0 / float(np.median(dts)) if len(dts) else 200.0
    fs = min(max(fs, 20.0), 1000.0)

    grid, g = resample(t, imu, valid, fs)
    calib_n = max(int(CFG["calib_s"] * fs), 1)
    q = attitude(g[:, 0:3], g[:, 3:6], fs, calib_n)
    acc_w = qrot(q, g[:, 3:6])
    del g
    head = acc_w[:calib_n]
    g_mag = float(np.linalg.norm(head.mean(axis=0))) if len(head) else G
    acc_w[:, 2] -= g_mag
    p = band_integrate(acc_w, fs)
    del acc_w

    # back onto every input timestamp
    for ax in range(3):
        pos[:, ax] = np.interp(t, grid, p[:, ax])
    for ax in range(4):
        quat[:, ax] = np.interp(t, grid, q[:, ax])

    # rows after the last valid sample: dead ending, coast
    end = grid[-1]
    after = t > end
    if after.any():
        m = max(int(0.5 * fs), 2)
        v_end = (p[-1] - p[-m]) / ((m - 1) / fs) if len(p) > m else np.zeros(3)
        pos[after] = coast(p[-1], v_end, t[after] - end)
        quat[after] = q[-1]
    quat /= np.linalg.norm(quat, axis=1, keepdims=True)
    return pos, quat


def main(argv):
    if len(argv) < 2:
        raise SystemExit("usage: python main.py <imu csv | folder | zip> [output txt]")
    src = argv[1]
    dst = argv[2] if len(argv) > 2 else "estimated_trajectory.txt"
    ts, imu = read_imu(src)
    pos, quat = estimate(ts, imu)
    del imu
    write(dst, ts, pos, quat)


if __name__ == "__main__":
    main(sys.argv)
