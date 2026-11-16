import math
import sys

G = 9.80665


def rotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2 * (y * vz - z * vy)
    ty = 2 * (z * vx - x * vz)
    tz = 2 * (x * vy - y * vx)
    return (vx + w * tx + y * tz - z * ty,
            vy + w * ty + z * tx - x * tz,
            vz + w * tz + x * ty - y * tx)


def tilt_from(acc):
    # rotation that takes the measured "up" to world z
    ax, ay, az = acc
    n = math.sqrt(ax * ax + ay * ay + az * az)
    ax, ay, az = ax / n, ay / n, az / n
    s = math.sqrt(2 * (1 + az))
    if s < 1e-6:
        return (1.0, 0.0, 0.0, 0.0)
    return (ay / s, -ax / s, 0.0, s / 2)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    rows = []
    with open(src) as f:
        for line in f:
            if line[0] != "#":
                c = line.split(",")
                rows.append((int(c[0]), [float(v) for v in c[1:7]]))

    t0 = rows[0][0]
    head = [r[1] for r in rows if r[0] - t0 < 2_000_000_000]
    q = tilt_from([sum(r[i] for r in head) / len(head) for i in (3, 4, 5)])

    p = [0.0, 0.0, 0.0]
    v = [0.0, 0.0, 0.0]
    prev = t0
    with open(dst, "w", newline="\n") as out:
        for ts, (gx, gy, gz, ax, ay, az) in rows:
            dt = (ts - prev) * 1e-9
            prev = ts
            dead = gx == gy == gz == ax == ay == az == 0.0
            if dt > 0 and not dead:
                x, y, z, w = q
                hx, hy, hz = 0.5 * gx * dt, 0.5 * gy * dt, 0.5 * gz * dt
                q = (x + w * hx + y * hz - z * hy,
                     y + w * hy + z * hx - x * hz,
                     z + w * hz + x * hy - y * hx,
                     w - x * hx - y * hy - z * hz)
                n = math.sqrt(sum(c * c for c in q))
                q = tuple(c / n for c in q)
                a = rotate(q, (ax, ay, az))
                v[0] += a[0] * dt
                v[1] += a[1] * dt
                v[2] += (a[2] - G) * dt
            if dt > 0:
                p[0] += v[0] * dt
                p[1] += v[1] * dt
                p[2] += v[2] * dt
            out.write(f"{ts // 10**9}.{ts % 10**9:09d} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} "
                      f"{q[0]:.7f} {q[1]:.7f} {q[2]:.7f} {q[3]:.7f}\n")


if __name__ == "__main__":
    main()
