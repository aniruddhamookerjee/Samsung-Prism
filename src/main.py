"""Track 3 Path Finder: 6-DoF trajectory from a degraded IMU recording.

    python src/main.py <imu csv | folder | zip> [estimated_trajectory.txt]

Input is EuRoC imu0/data.csv (timestamp ns, gyro rad/s, accel m/s^2). Output is
TUM format, one pose per input row, timestamps copied exactly from the input.

Pipeline
    1. read      stream the CSV into compact float32 arrays
    2. clean     drop duplicate, stuck and spiked rows, find the dead ending
    3. resample  valid rows onto a uniform grid, gaps bridged by interpolation
    4. attitude  gyro bias and initial tilt from the still stretch at the start,
                 gyro integrated at full rate, then the tilt pulled back to
                 gravity offline using a long average of world acceleration
                 (shorter where the gyro is noisy, never across a long gap)
    5. position  world acceleration averaged down to 20 Hz, double-integrated
                 in the frequency domain inside a band-pass, so slow drift from
                 bias and tilt error never builds up; slow horizontal motion is
                 shrunk hardest, and everything fades where the gyro is noise
                 on a multirotor (detected from motor buzz), slow horizontal
                 motion comes instead from rotor drag: the accelerometer axes
                 across the thrust read -0.2 x velocity, so velocity is measured
                 directly and only integrated once
    6. blind     after the sensor dies, coast briefly, then head for the
                 estimated start point, averaged over the first 12 s
                 (the practice flights end where they began)
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
    "calib_s": 2.0,        # longest start window used for gyro bias and initial tilt,
                           # cut short as soon as the device moves
    "bias_iters": 4,       # rounds of gyro-bias fitting from the tilt drift (0 = off)
    "bias_min": 0.03,      # rad/s: a smaller fitted bias is noise, not bias (TUM-VI fits 0.013 at most)
    "bias_settle": 0.01,   # rad/s: the last round must change the bias less than this
    "bias_fit_always": 0,  # 0 = only when there is no still start to read the bias from
    "bias_ridge": 1e-3,    # pulls weakly seen bias components towards no change
    "bias_max": 0.2,       # rad/s, largest correction one round may make
    "still_acc_std": 1.0,  # m/s^2 of accel jitter still counted as standing (motors idling)
    "tilt_window_s": 30.0, # averaging window for the gravity direction
    "tilt_window_noisy_s": 8.0,   # the same where the gyro is mostly noise
    "band_lo_hz": 0.02,    # position keeps motion above this frequency ...
    "band_hi_hz": 0.04,    # ... fully above this one, with a smooth ramp between
    "lp_hz": 3.0,          # above this, acceleration is vibration
    "gain": 0.25,          # horizontal shrink below split_hz: a too-large path costs more than a small one
    "gain_hi": 0.9,        # horizontal shrink above split_hz
    "split_hz": 0.08,
    "z_gain": 0.3,         # vertical shrink below split_hz
    "z_gain_hi": 0.9,      # vertical shrink above split_hz
    "z_band_lo_hz": 0.02,  # vertical pass band starts here
    "coast_tau_s": 0.6,    # blind segment: velocity decays with this time constant
    "return_tau_s": 1.0,   # blind segment: move to the target with this time constant
    "blind_home": 1.0,     # blind target: 0 = path centre, 1 = estimated start point
    "home_s": 12.0,        # the start point is the mean over this many seconds
    "drag": 1,             # use rotor drag for horizontal velocity when the file looks like a multirotor
    "drag_vib": 0.7,       # m/s^2 of motor buzz that marks a multirotor
    "drag_k": 0.2,         # 1/s, rotor drag constant (EuRoC fits 0.18 to 0.22)
    "drag_smooth_s": 0.5,  # s, averaging of the lateral acceleration
    "drag_cross_hz": 0.08, # below this, horizontal position comes from drag velocity
    "drag_lo_hz": 0.01,    # drag velocity is integrated above this
    "drag_gain": 0.45,     # shrink, for the same reason as gain
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


def seconds_to_ns(text):
    """'1403636579.758555392' -> 1403636579758555392 exactly, no float rounding."""
    text = text.strip()
    if "e" in text.lower():
        return int(round(float(text) * 1e9))
    whole, _, frac = text.partition(".")
    if not whole.lstrip("+-").isdigit() and whole not in ("", "-", "+"):
        raise ValueError(text)
    sign = -1 if whole.startswith("-") else 1
    frac = (frac + "000000000")[:9]
    if not frac.isdigit():
        raise ValueError(text)
    return sign * (abs(int(whole or "0")) * 1000000000 + int(frac))


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
                try:  # a timestamp in seconds, or a header without '#'
                    t = seconds_to_ns(c[0])
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


def still_prefix(g, fs):
    """Samples at the start before the device first moves, up to calib_s.

    Checked in quarter-second windows: the gyro and the accelerometer must
    both be quiet. Returns 0 when it is moving from the first sample.
    """
    w = max(int(0.25 * fs), 2)
    limit = min(int(CFG["calib_s"] * fs), len(g))
    n = 0
    while n + w <= limit:
        x = g[n:n + w].astype(np.float64)
        sd = x.std(axis=0)
        if math.sqrt(float((sd[0:3] ** 2).sum())) > 0.05 or math.sqrt(float((sd[3:6] ** 2).sum())) > CFG["still_acc_std"]:
            break
        n += w
    return n


def fit_bias(q, g, fs, d, bgap, seg):
    """Gyro bias left over in q, read from how fast its tilt drifts.

    A body-frame bias error b makes the integrated attitude drift away from
    gravity at R(t) b (world frame, horizontal part). The tilt correction
    measures that drift as phi(t), so phi(t) = phi0 - integral(R b dt), with a
    fresh phi0 after every long gap. Linear least squares in b, both sides
    smoothed alike. Rotating about different body axes over the recording is
    what makes all three components visible; a small ridge keeps the poorly
    seen ones near zero.
    """
    nb = len(q) // d
    if nb < 20:
        return np.zeros(3)
    win = max(int(CFG["tilt_window_s"] * fs / d), 1)
    w = (~bgap).astype(float)
    up = smooth_segments(block_world_acc(q, g[:, 3:6], d), win, seg, w)
    c = arc_to_z(up)
    phi = 2.0 * c[:, 0:2] / np.maximum(c[:, 3:4], 1e-6)

    qb = q[d // 2::d][:nb].astype(np.float64)
    x, y, z, wq = qb[:, 0], qb[:, 1], qb[:, 2], qb[:, 3]
    rows = np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * wq), 2 * (x * z + y * wq),
                     2 * (x * y + z * wq), 1 - 2 * (x * x + z * z), 2 * (y * z - x * wq)], axis=1)
    m = np.cumsum(rows, axis=0) * (d / fs)
    m = smooth_segments(m, win, seg, w)

    nseg = int(seg.max()) + 1 if len(seg) else 1
    k = 2 * nseg + 3
    ata = np.zeros((k, k))
    atb = np.zeros(k)
    for ax in range(2):
        a = np.zeros((nb, k))
        a[np.arange(nb), 2 * seg + ax] = 1.0
        a[:, 2 * nseg:] = -m[:, 3 * ax:3 * ax + 3]
        aw = a * w[:, None]
        ata += aw.T @ a
        atb += aw.T @ phi[:, ax]
    ridge = CFG["bias_ridge"] * w.sum() * (d / fs) ** 2 * win ** 2
    ata[2 * nseg:, 2 * nseg:] += ridge * np.eye(3)
    try:
        sol = np.linalg.solve(ata, atb)
    except np.linalg.LinAlgError:
        return np.zeros(3)
    db = sol[2 * nseg:]
    lim = CFG["bias_max"]
    return np.clip(db, -lim, lim)


def attitude(g, fs, d, calib_n, bgap, seg):
    bias = g[:calib_n, 0:3].astype(np.float64).mean(axis=0) if calib_n > 0 else np.zeros(3)
    head = max(calib_n, min(int(0.25 * fs), len(g)), 1)
    q0 = arc_to_z(g[:head, 3:6].astype(np.float64).mean(axis=0, keepdims=True))[0]
    q = integrate_gyro(g[:, 0:3], q0, fs, bias)
    # no still start to read the bias from: fit it from the tilt drift, and
    # keep the fit only if it settles on a plausible value
    rounds = int(CFG["bias_iters"]) if (calib_n == 0 or CFG["bias_fit_always"]) else 0
    if rounds:
        start = bias.copy()
        db = np.zeros(3)
        for _ in range(rounds):
            db = fit_bias(q, g, fs, d, bgap, seg)
            bias = bias + db
            q = integrate_gyro(g[:, 0:3], q0, fs, bias)
        settled = float(np.abs(db).max()) < CFG["bias_settle"]
        size = float(np.sqrt((bias * bias).sum()))
        plausible = float(np.abs(bias).max()) < CFG["bias_max"] * 0.75 and size > CFG["bias_min"]
        if not (settled and plausible):
            bias = start
            q = integrate_gyro(g[:, 0:3], q0, fs, bias)

    # offline tilt correction: averaged over tens of seconds, world acceleration
    # is gravity alone, so rotate each pose until that average points up
    # where the gyro is mostly noise its bias wanders faster, so a shorter
    # window is blended in there
    if len(q) >= d:
        win = max(int(CFG["tilt_window_s"] * fs / d), 1)
        short = max(int(CFG["tilt_window_noisy_s"] * fs / d), 1)
        w = (~bgap).astype(float)
        trust = gyro_quality(g[:, 0:3], d)[:, None]
        for _ in range(2):
            acc_w = block_world_acc(q, g[:, 3:6], d)
            up = smooth_segments(acc_w, win, seg, w)
            if trust.min() < 0.98:
                up = trust * up + (1.0 - trust) * smooth_segments(acc_w, short, seg, w)
            del acc_w
            apply_correction(q, arc_to_z(up), d)
    return q


# ---------------------------------------------------------------- 5. position

def block_body_acc(acc, d):
    """Body-frame acceleration averaged over blocks of d samples."""
    nb = len(acc) // d
    out = np.empty((nb, 3))
    step = max(CHUNK // d, 1) * d
    for s in range(0, nb * d, step):
        e = min(s + step, nb * d)
        out[s // d:e // d] = acc[s:e].astype(np.float64).reshape(-1, d, 3).mean(axis=1)
    return out


def vibration(acc, d):
    """Median spread of the accelerometer inside blocks of d samples (motor buzz)."""
    nb = len(acc) // d
    if nb < 1:
        return 0.0
    step = max(nb // 2000, 1)
    idx = np.arange(0, nb, step)
    b = acc[:nb * d].reshape(nb, d, 3)[idx].astype(np.float64)
    b = b[np.any(b != 0, axis=(1, 2))]
    if len(b) == 0:
        return 0.0
    return median(np.sqrt(((b - b.mean(axis=1, keepdims=True)) ** 2).sum(axis=2).mean(axis=1)))


def drag_velocity(q, acc, d, fs, bgap):
    """Horizontal world velocity from rotor drag, or None when it does not apply.

    On a multirotor the thrust is along one body axis, so the accelerometer's
    two other axes measure only rotor drag, which is -k times the velocity
    along them: velocity with no integration in it, so no drift. Every EuRoC
    recording fits k = 0.18 to 0.22 per second against the ground truth. A
    file counts as a multirotor when its accelerometer carries motor buzz
    (EuRoC 1.1 to 1.9 m/s^2, handheld TUM-VI 0.2 to 0.4).
    """
    if vibration(acc, d) < CFG["drag_vib"]:
        return None
    ab = block_body_acc(acc, d)
    nb = len(ab)
    ok = ~bgap[:nb]
    if ok.sum() < int(20 * fs):
        return None
    thrust = int(np.argmax(np.abs(ab[ok].mean(axis=0))))
    vbody = np.zeros((nb, 3))
    sm = max(int(CFG["drag_smooth_s"] * fs), 1)
    for k in range(3):
        if k == thrust:
            continue
        x = smooth(ab[:, k:k + 1], sm)[:, 0]
        vbody[:, k] = -(x - x[ok].mean()) / CFG["drag_k"]
    vbody[~ok] = 0.0
    qb = q[(np.arange(nb) * d + d // 2)].astype(np.float64)
    return qrot(qb, vbody)


def band_integrate(a, fs, vel=None):
    """Position from acceleration: divide by -(2 pi f)^2 inside a smooth pass band.

    With vel (horizontal world velocity from rotor drag), slow horizontal
    motion comes from integrating that velocity once, and the acceleration
    only supplies what is faster than drag_cross_hz.
    """
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
    z_gain = base * ramp(CFG["z_band_lo_hz"], 2 * CFG["z_band_lo_hz"]) * (
        CFG["z_gain"] + (CFG["z_gain_hi"] - CFG["z_gain"]) * ramp(split / 1.5, split * 1.5))

    if vel is not None:
        cross = 1.0 - ramp(CFG["drag_cross_hz"] / 1.5, CFG["drag_cross_hz"] * 1.5)
        a_gain = base * (1.0 - cross) * CFG["gain_hi"]
        v_gain = np.zeros(len(f), complex)
        v_gain[nz] = cross[nz] * ramp(CFG["drag_lo_hz"], 2 * CFG["drag_lo_hz"])[nz] * CFG["drag_gain"] / (
            2j * math.pi * f[nz])
        vel = vel - vel.mean(axis=0)

    p = np.empty((n, 3))
    buf = np.zeros(nfft)
    for ax in range(3):
        buf[:] = 0.0
        buf[pad:pad + n] = a[:, ax] * taper
        spec = np.fft.rfft(buf)
        if ax < 2 and vel is not None:
            spec *= a_gain
            buf[:] = 0.0
            buf[pad:pad + n] = vel[:, ax] * taper
            spec += np.fft.rfft(buf) * v_gain
        else:
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
        # practice flights end where they began (landing pad, loop), so head
        # for a blend of the estimated start point and the path centre
        n0 = max(1, min(len(p), int(CFG["home_s"] * CFG["pos_hz"])))
        target = CFG["blind_home"] * p[:n0].mean(axis=0)
        pos[after] = target + (p[-1] - target) * back + k[:, None] * v_end
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
    calib_n = still_prefix(g, fs)
    bgap, seg = block_flags(gap, d)
    del gap
    q = attitude(g, fs, d, calib_n, bgap, seg)

    if len(q) >= 2 * d:
        acc_w = block_world_acc(q, g[:, 3:6], d)
        cb = max(max(calib_n, int(0.25 * fs)) // d, 1)
        g_mag = float(np.linalg.norm(acc_w[:cb].mean(axis=0)))
        acc_w[:, 2] -= g_mag
        acc_w[bgap] = 0.0          # nothing was measured there
        drag = drag_velocity(q, g[:, 3:6], d, fs / d, bgap) if CFG["drag"] else None
        p = band_integrate(acc_w, fs / d, drag)
        p *= gyro_quality(g[:, 0:3], d)[:, None]
        pt = grid0 + (np.arange(len(p)) + 0.5) * d / fs
        del acc_w
    else:
        p = np.zeros((1, 3))
        pt = np.array([grid0])
    del g
    return {"grid0": grid0, "fs": fs, "q": q, "pt": pt, "p": p}


USAGE = """usage: python main.py <imu csv | folder | zip> [output txt]

Reads a degraded EuRoC IMU recording (imu0/data.csv: timestamp ns, gyro rad/s,
accel m/s^2) and writes one TUM pose per input row:
    timestamp tx ty tz qx qy qz qw
The output defaults to estimated_trajectory.txt in the current folder."""


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(USAGE)
        return
    src = argv[1]
    dst = argv[2] if len(argv) > 2 else "estimated_trajectory.txt"
    if not os.path.exists(src):
        raise SystemExit(f"input not found: {src}\n\n{USAGE}")
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
