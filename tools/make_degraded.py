import argparse
import json
from pathlib import Path

import pandas as pd

from degrade_imu import CONFIG, SEED, degrade

EUROC_HEADER = (
    "#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],"
    "a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]"
)
GYRO = ["gx", "gy", "gz"]
ACC = ["ax", "ay", "az"]


def degrade_file(imu_csv, out_dir, raw_order=False, cfg=None, seconds=None):
    cfg = {**CONFIG, **(cfg or {})}
    df = pd.read_csv(imu_csv, comment="#", header=None,
                     names=["timestamp"] + GYRO + ACC)
    if seconds is not None:
        df = df[df["timestamp"] - df["timestamp"].iloc[0] <= seconds * 1e9].reset_index(drop=True)
    if raw_order:
        out, stats = degrade(df, cfg, SEED)
    else:
        out, stats = degrade(df[["timestamp"] + ACC + GYRO], cfg, SEED,
                             ts_unit="ns", accel_unit="ms2")
        out = out[["timestamp"] + GYRO + ACC]
    stats["raw_order"] = raw_order

    dst = Path(out_dir) / "imu0"
    dst.mkdir(parents=True, exist_ok=True)
    with open(dst / "data.csv", "w", newline="\n") as f:
        f.write(EUROC_HEADER + "\n")
        out.to_csv(f, index=False, header=False, lineterminator="\n")
    with open(Path(out_dir) / "meta.json", "w") as f:
        json.dump(stats, f, indent=2)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("imu_csv", help="clean EuRoC imu0/data.csv")
    ap.add_argument("out_dir", help="writes <out_dir>/imu0/data.csv and meta.json")
    ap.add_argument("--raw-order", action="store_true",
                    help="feed EuRoC column order to the script as it is")
    ap.add_argument("--max-level", type=float, default=None)
    ap.add_argument("--gamma", type=float, default=None)
    ap.add_argument("--burst-len", type=int, nargs=2, default=None, metavar=("LO", "HI"))
    args = ap.parse_args()

    cfg = dict(CONFIG)
    if args.max_level is not None:
        cfg["max_level"] = args.max_level
    if args.gamma is not None:
        cfg["gamma"] = args.gamma
    if args.burst_len is not None:
        cfg["burst_len"] = tuple(args.burst_len)

    stats = degrade_file(args.imu_csv, args.out_dir, args.raw_order, cfg)
    print(f"{stats['rows_in']} -> {stats['rows_out']} rows, "
          f"{stats['dropped_total']} dropped, {stats['duplicated_rows']} duplicated, "
          f"{stats['failure_frames']} zeroed at the end")


if __name__ == "__main__":
    main()
