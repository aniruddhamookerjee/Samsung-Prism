"""Score src/main.py settings in-process, for quick sweeps.

    python tools/tune.py                         # current settings, every set
    python tools/tune.py gain=0.5 band_lo_hz=0.1  # override CFG values
    python tools/tune.py --sets degraded stress/gaps2s

Uses the same metrics as score.py, but skips runtime and memory.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import main as est  # noqa: E402
from score import metrics  # noqa: E402


def load(seq_dir):
    ts, imu = est.read_imu(str(seq_dir / "imu0" / "data.csv"))
    return ts, imu


def run(sets, overrides, cache):
    est.CFG.update(overrides)
    rows = []
    for s in sets:
        d = ROOT / "data" / s
        for seq in sorted(p for p in d.iterdir() if (p / "imu0" / "data.csv").exists()):
            key = (s, seq.name)
            if key not in cache:
                cache[key] = load(seq) + (np.loadtxt(ROOT / "data/clean" / seq.name / "gt.tum"),)
            ts, imu, gt = cache[key]
            pos, quat = est.estimate(ts, imu.copy())
            e = np.column_stack([ts * 1e-9, pos, quat])
            m = metrics(e, gt, ts, imu, 1.0)
            rows.append((s, seq.name, m))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set", nargs="*", help="key=value overrides of CFG")
    ap.add_argument("--sets", nargs="+", default=["degraded", "degraded_raw"])
    a = ap.parse_args()
    ov = {}
    for kv in a.set:
        k, v = kv.split("=")
        ov[k] = float(v)
    rows = run(a.sets, ov, {})
    keys = ["ate_m", "blind_m", "gap_m", "rpe_1s_m", "rot_deg"]
    print(f"{'set':14s}{'seq':18s}" + "".join(f"{k:>10s}" for k in keys))
    for s, seq, m in rows:
        print(f"{s:14s}{seq:18s}" + "".join(f"{m.get(k, float('nan')):10.3f}" for k in keys))
    for k in ("ate_m", "blind_m", "gap_m"):
        v = [m[k] for _, _, m in rows if k in m and np.isfinite(m[k])]
        print(f"mean {k}: {np.mean(v):.3f}")


if __name__ == "__main__":
    main()
