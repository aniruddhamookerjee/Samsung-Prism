import sys


def sec(ns):
    ns = int(ns)
    return f"{ns // 10**9}.{ns % 10**9:09d}"


def main():
    src, dst = sys.argv[1], sys.argv[2]
    n = 0
    with open(src) as f, open(dst, "w", newline="\n") as out:
        out.write("# timestamp tx ty tz qx qy qz qw\n")
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            c = line.strip().split(",")
            t, p, qw, qxyz = c[0], c[1:4], c[4], c[5:8]
            out.write(" ".join([sec(t), *p, *qxyz, qw]) + "\n")
            n += 1
    print(f"{n} poses -> {dst}")


if __name__ == "__main__":
    main()
