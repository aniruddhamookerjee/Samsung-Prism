import argparse
from pathlib import Path

from gt_to_tum import convert
from make_degraded import degrade_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", default="data/clean")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    for seq in sorted(p for p in Path(args.clean).iterdir() if (p / "imu.csv").exists()):
        convert(seq / "gt.csv", seq / "gt.tum")
        for name, raw in (("degraded", False), ("degraded_raw", True)):
            s = degrade_file(seq / "imu.csv", Path(args.out) / name / seq.name, raw_order=raw)
        print(f"{seq.name}: {s['duration_s']:.0f} s, {s['rows_in']} -> {s['rows_out']} rows, "
              f"{s['dropped_total']} dropped, {s['duplicated_rows']} duplicated")


if __name__ == "__main__":
    main()
