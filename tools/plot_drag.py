"""Picture of the rotor-drag idea, for the slides: sideways acceleration vs true velocity.

    python tools/plot_drag.py                                   # V1_02_medium, writes docs/figures/drag.png
    python tools/plot_drag.py --imu data/clean/MH_04_difficult/imu.csv --gt data/clean/MH_04_difficult/gt.tum

Left: over one flight, velocity read from the accelerometer (-a / 0.2, across the
thrust direction) against the ground-truth velocity in the same direction.
Right: the same as a scatter, flight samples only, with the fitted slope.
"""

import argparse
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def rotm(q):
    x, y, z, w = q.T
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


def lp(x, n):
    k = np.ones(n) / n
    return np.column_stack([np.convolve(x[:, i], k, "same") for i in range(x.shape[1])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imu", default=str(ROOT / "data/clean/V1_02_medium/imu.csv"))
    ap.add_argument("--gt", default=str(ROOT / "data/clean/V1_02_medium/gt.tum"))
    ap.add_argument("--k", type=float, default=0.2)
    ap.add_argument("--out", default=str(ROOT / "docs/figures/drag.png"))
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    raw = np.loadtxt(a.imu, delimiter=",", comments="#")
    gt = np.loadtxt(a.gt)
    t = (raw[:, 0] - raw[0, 0]) * 1e-9
    tg = gt[:, 0] - raw[0, 0] * 1e-9
    fs = 200.0
    tt = np.arange(max(tg[0], t[0]) + 1, min(tg[-1], t[-1]) - 1, 1 / fs)
    pos = np.column_stack([np.interp(tt, tg, gt[:, k]) for k in (1, 2, 3)])
    qs = np.column_stack([np.interp(tt, tg, gt[:, k]) for k in (4, 5, 6, 7)])
    qs /= np.linalg.norm(qs, axis=1, keepdims=True)
    v = np.gradient(pos, 1 / fs, axis=0)
    vb = lp(np.einsum("nji,nj->ni", rotm(qs), v), 100)
    ab = lp(np.column_stack([np.interp(tt, t, raw[:, k]) for k in (4, 5, 6)]), 100)
    fly = np.linalg.norm(lp(v, 200), axis=1) > 0.05
    u = ab[fly].mean(0)
    u /= np.linalg.norm(u)
    e1 = np.array([0.0, 1.0, 0.0]) - u[1] * u
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u, e1)

    fig, axes = plt.subplots(2, 2, figsize=(13, 6.4), gridspec_kw={"width_ratios": [2.6, 1]})
    for row, (e, name) in enumerate(((e1, "side axis 1"), (e2, "side axis 2"))):
        acc = ab @ e
        acc = acc - acc[fly].mean()
        vel = vb @ e
        est = -acc / a.k
        r = np.corrcoef(est[fly], vel[fly])[0, 1]
        k_fit = -np.sum(acc[fly] * vel[fly]) / np.sum(vel[fly] ** 2)
        ax = axes[row, 0]
        ax.plot(tt, vel, color="#888888", lw=1.4, label="true velocity (motion capture)")
        ax.plot(tt, est, color="#1f6fd1", lw=1.0, label=f"accelerometer / -{a.k:g}, no integration")
        ax.set_ylabel(f"{name} (m/s)")
        ax.legend(loc="upper right", fontsize=8)
        if row == 1:
            ax.set_xlabel("time (s)")
        ax = axes[row, 1]
        ax.scatter(vel[fly][::20], acc[fly][::20], s=3, color="#1f6fd1", alpha=0.4)
        x = np.linspace(vel[fly].min(), vel[fly].max(), 10)
        ax.plot(x, -k_fit * x, color="#d1491f", lw=1.5, label=f"slope -{k_fit:.2f}/s, r = {abs(r):.2f}")
        ax.set_xlabel("true velocity (m/s)")
        ax.set_ylabel("acceleration (m/s^2)")
        ax.legend(loc="upper right", fontsize=8)
    fig.suptitle(f"{Path(a.imu).parent.name}: on a drone the accelerometer measures velocity "
                 "(rotor drag, read across the thrust direction)")
    fig.tight_layout()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(out)


if __name__ == "__main__":
    main()
