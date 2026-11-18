"""Picture of an estimated path against the ground truth, for the slides and video.

    python tools/plot_path.py data/degraded/V1_02_medium            # writes results/V1_02_medium.png
    python tools/plot_path.py data/stress/gaps2s/tumvi_room1 --out x.png

Runs src/main.py, aligns the result to the ground truth the same way the
scorer does, and draws a top view plus height over time, with the dropouts
and the blind 5 s shaded.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from score import align  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq_dir", help="folder holding imu0/data.csv")
    ap.add_argument("--gt", default=None, help="ground truth tum file (default data/clean/<name>/gt.tum)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    seq = Path(a.seq_dir)
    src = seq / "imu0" / "data.csv"
    gt_path = Path(a.gt) if a.gt else ROOT / "data" / "clean" / seq.name / "gt.tum"
    out = Path(a.out) if a.out else ROOT / "results" / f"{seq.name}.png"

    with tempfile.TemporaryDirectory() as tmp:
        est_path = Path(tmp) / "est.txt"
        subprocess.run([sys.executable, str(ROOT / "src" / "main.py"), str(src), str(est_path)], check=True)
        est = np.loadtxt(est_path)
    gt = np.loadtxt(gt_path)
    imu = np.loadtxt(src, delimiter=",", comments="#", usecols=range(1, 7))
    t = est[:, 0]

    i = np.clip(np.searchsorted(gt[:, 0], t), 1, len(gt) - 1)
    i -= (t - gt[i - 1, 0]) < (gt[i, 0] - t)
    ok = np.abs(gt[i, 0] - t) < 0.01
    r, tr = align(est[ok, 1:4], gt[i[ok], 1:4])
    p = est[:, 1:4] @ r.T + tr
    g = gt[i, 1:4]
    err = np.sqrt((np.linalg.norm(p[ok] - g[ok], axis=1) ** 2).mean())
    still = g[ok].mean(axis=0)
    err_still = np.sqrt((np.linalg.norm(g[ok] - still, axis=1) ** 2).mean())

    alive = np.flatnonzero(np.any(imu != 0, axis=1))
    blind_from = t[alive[-1] + 1] if alive[-1] + 1 < len(t) else None
    dt = np.diff(t)
    gaps = [(t[k], t[k + 1]) for k in np.flatnonzero(dt > 4 * np.median(dt[dt > 0]))]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1, 1.4]})
    ax1.plot(g[ok, 0], g[ok, 1], color="#888888", lw=1.4, label="ground truth")
    ax1.plot(p[:, 0], p[:, 1], color="#1f6fd1", lw=1.1, label="our estimate")
    ax1.scatter([still[0]], [still[1]], color="#d1491f", marker="x", s=70, zorder=5, label="stay-still")
    if blind_from is not None:
        b = t >= blind_from
        ax1.plot(p[b, 0], p[b, 1], color="#e0a000", lw=3, label="blind 5 s")
    ax1.set_aspect("equal", adjustable="datalim")
    ax1.set_xlabel("x (m)")
    ax1.set_ylabel("y (m)")
    ax1.set_title("top view")
    ax1.legend(loc="best", fontsize=8)

    t0 = t[0]
    ax2.plot(t[ok] - t0, g[ok, 2], color="#888888", lw=1.4, label="ground truth")
    ax2.plot(t - t0, p[:, 2], color="#1f6fd1", lw=1.1, label="our estimate")
    for a0, a1 in gaps:
        ax2.axvspan(a0 - t0, a1 - t0, color="#d1491f", alpha=0.15, lw=0)
    if blind_from is not None:
        ax2.axvspan(blind_from - t0, t[-1] - t0, color="#e0a000", alpha=0.25, lw=0, label="blind 5 s")
    ax2.set_xlabel("time (s)")
    ax2.set_ylabel("height z (m)")
    ax2.set_title(f"height  (dropouts shaded red, {len(gaps)} of them)")
    ax2.legend(loc="best", fontsize=8)

    fig.suptitle(f"{seq.parent.name}/{seq.name}: path error {err:.2f} m, stay-still {err_still:.2f} m")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"{out}  ate {err:.3f} m, stay-still {err_still:.3f} m")


if __name__ == "__main__":
    main()
