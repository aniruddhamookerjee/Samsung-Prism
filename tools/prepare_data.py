import argparse
from pathlib import Path

from gt_to_tum import convert
from make_degraded import degrade_file

# harsher than the organisers' defaults, to see what breaks
STRESS = {
    "gaps2s": {"cfg": {"burst_len": (5, 400), "burst_prob_max": 0.003}},
    "harsh": {"cfg": {"max_level": 2.0}},
    "early": {"cfg": {"gamma": 0.7}},
    "harsh_raw": {"cfg": {"max_level": 2.0}, "raw_order": True},
    "short10": {"seconds": 10},
    "short3": {"seconds": 3},
    "tiny": {"seconds": 0.02},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", default="data/clean")
    ap.add_argument("--out", default="data")
    ap.add_argument("--stress", action="store_true", help="also write data/stress/<set>/")
    args = ap.parse_args()
    out = Path(args.out)

    for seq in sorted(p for p in Path(args.clean).iterdir() if (p / "imu.csv").exists()):
        convert(seq / "gt.csv", seq / "gt.tum")
        for name, raw in (("degraded", False), ("degraded_raw", True)):
            s = degrade_file(seq / "imu.csv", out / name / seq.name, raw_order=raw)
        print(f"{seq.name}: {s['duration_s']:.0f} s, {s['rows_in']} -> {s['rows_out']} rows, "
              f"{s['dropped_total']} dropped, {s['duplicated_rows']} duplicated")
        if not args.stress:
            continue
        for name, kw in STRESS.items():
            s = degrade_file(seq / "imu.csv", out / "stress" / name / seq.name, **kw)
            print(f"  {name}: {s['rows_out']} rows, {s['dropped_total']} dropped, "
                  f"{s['dropped_burst_gaps']} bursts, {s['spikes']} spikes, "
                  f"{s['failure_frames']} zeroed")


if __name__ == "__main__":
    main()
