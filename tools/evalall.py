"""Score src/main.py settings over every local set at once, relative to stay-still.

    python tools/evalall.py                       # current settings
    python tools/evalall.py gain=0.3 split_hz=0.1 # CFG overrides
    python tools/evalall.py --groups tune       # only the tuning group (comma separated)

Each set is a folder of <name>/imu0/data.csv; the ground truth is read from
data/gt_all/<name>/gt.tum (or data/clean, data/holdout_clean, data/extra_clean).
Prints, per group, the mean of (ours / stay-still) for the path, the blind 5 s
and the dropouts, which is what the scoring cares about.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tune import est, est_poses, load  # noqa: E402
from score import metrics  # noqa: E402

GROUPS = {
    "tune": ["degraded", "degraded_raw", "stress/early", "stress/gaps2s", "stress/harsh", "stress/harsh_raw"],
    "holdout": ["holdout_all/degraded", "holdout_all/degraded_raw", "stress_mid"],
    "extra": ["extra/degraded", "extra/degraded_raw"],
}
GT_DIRS = ["gt_all", "clean", "holdout_clean", "extra_clean"]


def gt_for(name):
    for d in GT_DIRS:
        p = ROOT / "data" / d / name / "gt.tum"
        if p.exists():
            return np.loadtxt(p)
    return None


def still_metrics(ts, imu, gt):
    pos = np.zeros((len(ts), 3))
    quat = np.tile([0.0, 0.0, 0.0, 1.0], (len(ts), 1))
    return metrics(np.column_stack([ts * 1e-9, pos, quat]), gt, ts, imu, 1.0)


def run(groups, overrides, cache, verbose=False):
    est.CFG.update(overrides)
    out = {}
    for gname in groups:
        ratios = {"ate_m": [], "blind_m": [], "gap_m": []}
        for s in GROUPS[gname]:
            d = ROOT / "data" / s
            if not d.exists():
                continue
            for seq in sorted(p for p in d.iterdir() if (p / "imu0" / "data.csv").exists()):
                key = (s, seq.name)
                if key not in cache:
                    gt = gt_for(seq.name)
                    if gt is None:
                        continue
                    ts, imu = load(seq)
                    cache[key] = (ts, imu, gt, still_metrics(ts, imu, gt))
                ts, imu, gt, base = cache[key]
                pos, quat = est_poses(ts, imu)
                m = metrics(np.column_stack([ts * 1e-9, pos, quat]), gt, ts, imu, 1.0)
                row = []
                for k in ratios:
                    if k in m and np.isfinite(m[k]) and np.isfinite(base.get(k, np.nan)) and base[k] > 0:
                        ratios[k].append(m[k] / base[k])
                        row.append(f"{k[:-2]} {m[k]:.3f}/{base[k]:.3f}")
                if verbose:
                    print(f"  {s:26s}{seq.name:18s}" + "  ".join(row))
        out[gname] = {k: (float(np.mean(v)) if v else float("nan"), float(np.max(v)) if v else float("nan"), len(v))
                      for k, v in ratios.items()}
    return out


def show(res):
    for g, r in res.items():
        print(f"{g:8s}" + "  ".join(f"{k[:-2]} {m:.3f} (max {x:.2f}, n={n})" for k, (m, x, n) in r.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set", nargs="*")
    ap.add_argument("--groups", default=",".join(GROUPS), help="comma separated")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    ov = {k: float(v) for k, v in (kv.split("=") for kv in a.set)}
    show(run(a.groups.split(","), ov, {}, a.v))


if __name__ == "__main__":
    main()
