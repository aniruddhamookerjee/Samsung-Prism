import argparse
import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np

RUNNER = Path(__file__).with_name("_run.py")
FIELDS = ["date", "label", "set", "seq", "format", "ate_m", "blind_m", "gap_m",
          "rpe_1s_m", "rot_deg", "ms_per_s", "mem_mb", "mem_with_imports_mb"]


def run(script, src, dst, mode, timeout):
    try:
        p = subprocess.run([sys.executable, str(RUNNER), mode, str(script), str(src), str(dst)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout} s"}
    for line in p.stderr.splitlines():
        if line.startswith("@@"):
            return json.loads(line[2:])
    last = [l for l in p.stderr.splitlines() if l.strip()]
    return {"error": "crashed: " + (last[-1].strip() if last else f"exit code {p.returncode}")}


def read_est(path, ts_ns):
    if not Path(path).exists():
        return None, "no output file"
    rows = [l.split() for l in open(path) if l.strip() and not l.startswith("#")]
    if len(rows) != len(ts_ns):
        return None, f"{len(rows)} rows, input has {len(ts_ns)}"
    if any(len(r) != 8 for r in rows):
        return None, "not 8 columns"
    try:
        est = np.array(rows, dtype=float)
    except ValueError:
        return None, "not numbers"
    if not np.isfinite(est).all():
        return None, "nan or inf"
    if np.abs(est[:, 0] - ts_ns * 1e-9).max() > 1e-6:
        return est, "timestamps differ from input"
    if np.abs(np.linalg.norm(est[:, 4:8], axis=1) - 1).max() > 1e-3:
        return est, "quaternion not unit"
    return est, "ok"


def rotmat(q):
    x, y, z, w = (q / np.linalg.norm(q, axis=1, keepdims=True)).T
    return np.stack([
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y),
    ], axis=1).reshape(-1, 3, 3)


def align(pe, pg):
    """Rigid fit of est onto ground truth, same as evo -a. No rotation if est never moves."""
    me, mg = pe.mean(0), pg.mean(0)
    u, s, vt = np.linalg.svd((pg - mg).T @ (pe - me) / len(pe))
    if s[1] < 1e-9:
        r = np.eye(3)
    else:
        d = np.sign(np.linalg.det(u) * np.linalg.det(vt))
        r = u @ np.diag([1, 1, d]) @ vt
    return r, mg - r @ me


def rmse(err, mask=None):
    if mask is not None:
        err = err[mask]
    return float(np.sqrt((err ** 2).mean())) if len(err) else float("nan")


def metrics(est, gt, ts_ns, imu, gap_tail):
    t = est[:, 0]
    i = np.clip(np.searchsorted(gt[:, 0], t), 1, len(gt) - 1)
    i -= (t - gt[i - 1, 0]) < (gt[i, 0] - t)
    ok = np.abs(gt[i, 0] - t) < 0.01
    t, est, g = t[ok], est[ok], gt[i[ok]]
    if len(t) < 3:
        return {}

    r, tr = align(est[:, 1:4], g[:, 1:4])
    pe = est[:, 1:4] @ r.T + tr
    err = np.linalg.norm(pe - g[:, 1:4], axis=1)

    re, rg = r @ rotmat(est[:, 4:8]), rotmat(g[:, 4:8])
    cos = (np.einsum("nij,nij->n", rg, re) - 1) / 2
    rot = np.degrees(np.arccos(np.clip(cos, -1, 1)))

    tin = ts_ns * 1e-9
    dead = np.flatnonzero((imu != 0).any(axis=1))
    last = dead[-1] if len(dead) else -1
    blind_from = tin[last + 1] if last + 1 < len(tin) else np.inf
    blind = t >= blind_from

    dt = np.diff(tin)
    in_gap = np.zeros(len(t), bool)
    for k in np.flatnonzero(dt > 4 * np.median(dt[dt > 0])):
        in_gap |= (t >= tin[k]) & (t <= tin[k + 1] + gap_tail)
    in_gap &= ~blind

    j = np.searchsorted(t, t + 1.0)
    a = np.flatnonzero(j < len(t))
    b = j[a]
    keep = np.abs(t[b] - t[a] - 1.0) < 0.05
    a, b = a[keep], b[keep]
    de = np.einsum("nji,nj->ni", re[a], pe[b] - pe[a])
    dg = np.einsum("nji,nj->ni", rg[a], g[b, 1:4] - g[a, 1:4])

    return {
        "ate_m": rmse(err),
        "blind_m": rmse(err, blind),
        "gap_m": rmse(err, in_gap),
        "rpe_1s_m": rmse(np.linalg.norm(de - dg, axis=1)),
        "rot_deg": rmse(rot),
    }


def score(script, seq_dir, gt_path, out_dir, repeats, gap_tail, timeout):
    src = seq_dir / "imu0" / "data.csv"
    dst = out_dir / f"{seq_dir.parent.name}_{seq_dir.name}.txt"
    dst.unlink(missing_ok=True)
    ts_ns = np.loadtxt(src, delimiter=",", comments="#", usecols=0, dtype=np.int64, ndmin=1)
    imu = np.loadtxt(src, delimiter=",", comments="#", usecols=range(1, 7), ndmin=2)

    runs = [run(script, src, dst, "time", timeout) for _ in range(repeats)]
    bad = [r["error"] for r in runs if "error" in r]
    if bad:
        return {"format": bad[0]}
    mem = run(script, src, dst, "mem", timeout * 5)
    if "error" in mem:
        return {"format": mem["error"]}

    row = {
        "ms_per_s": 1000 * min(r["seconds"] for r in runs) / max((ts_ns[-1] - ts_ns[0]) * 1e-9, 1e-9),
        "mem_mb": (mem["peak"] - mem["base"]) / 2**20,
        "mem_with_imports_mb": mem["peak"] / 2**20,
    }
    est, row["format"] = read_est(dst, ts_ns)
    if est is not None:
        row.update(metrics(est, np.loadtxt(gt_path), ts_ns, imu, gap_tail))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script", help="estimator, run as: script <imu csv> <output txt>")
    ap.add_argument("--label", required=True, help="name for this version in the results table")
    ap.add_argument("--data", nargs="+", default=["data/degraded"])
    ap.add_argument("--gt", default="data/clean")
    ap.add_argument("--out", default="results")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--gap-tail", type=float, default=1.0,
                    help="seconds after each gap that count towards gap_m")
    ap.add_argument("--stress", action="store_true", help="score every set under data/stress instead")
    ap.add_argument("--timeout", type=float, default=120, help="seconds allowed per run")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out)
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    sets = [Path(d) for d in args.data]
    if args.stress:
        sets = sorted(p for p in Path("data/stress").iterdir() if p.is_dir())
    rows = []
    for data in sets:
        for seq_dir in sorted(p for p in data.iterdir() if (p / "imu0" / "data.csv").exists()):
            row = score(args.script, seq_dir, Path(args.gt) / seq_dir.name / "gt.tum",
                        out_dir / "runs", args.repeats, args.gap_tail, args.timeout)
            rows.append({"date": date.today().isoformat(), "label": args.label,
                         "set": data.name, "seq": seq_dir.name, **row})

    show = FIELDS[2:]
    text = [[f"{r[c]:.3f}" if isinstance(r.get(c), float) else str(r.get(c, "")) for c in show]
            for r in rows]
    width = [max(len(c), *(len(t[k]) for t in text)) for k, c in enumerate(show)]
    for line in [show] + text:
        print("  ".join(c.rjust(w) for c, w in zip(line, width)))

    if not args.no_save:
        table = out_dir / "results.csv"
        new = not table.exists()
        with open(table, "a", newline="") as f:
            w = csv.DictWriter(f, FIELDS)
            if new:
                w.writeheader()
            for r in rows:
                w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    main()
