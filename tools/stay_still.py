import sys

from gt_to_tum import sec


def main():
    src, dst = sys.argv[1], sys.argv[2]
    n = 0
    with open(src) as f, open(dst, "w", newline="\n") as out:
        out.write("# timestamp tx ty tz qx qy qz qw\n")
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            out.write(sec(line.split(",", 1)[0]) + " 0 0 0 0 0 0 1\n")
            n += 1
    print(f"{n} poses -> {dst}")


if __name__ == "__main__":
    main()
