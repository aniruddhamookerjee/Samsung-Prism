import argparse
import sys
import urllib.request
from pathlib import Path

URL = "https://vision.in.tum.de/tumvi/exported/euroc/512_16/dataset-{}_512_16.tar"
WANTED = {
    "mav0/imu0/data.csv": "imu.csv",
    "mav0/mocap0/data.csv": "gt.csv",
}
CHUNK = 1 << 20


class Tar:
    """Finds files in a remote tar by sampling it, instead of downloading the images."""

    def __init__(self, url):
        resp = self._get(url, 0, 0)
        self.url = resp.url
        self.size = int(resp.headers["Content-Range"].split("/")[1])
        self.found = {}
        self.probes = {}

    @staticmethod
    def _get(url, lo, hi):
        import ssl
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={
            "Range": f"bytes={lo}-{hi}", "User-Agent": "Mozilla/5.0"})
        return urllib.request.urlopen(req, timeout=300, context=ctx)

    def read(self, lo, n):
        return self._get(self.url, lo, lo + n - 1).read()

    def probe(self, off):
        """Folders of the first and last tar headers seen in one chunk at off."""
        if off not in self.probes:
            data = self.read(off, min(CHUNK, self.size - off))
            dirs = []
            for i in range(0, len(data) - 511, 512):
                h = data[i:i + 512]
                if h[257:262] != b"ustar":
                    continue
                if sum(h[:148]) + sum(h[156:]) + 8 * 32 != int(h[148:156].strip(b"\0 ") or b"0", 8):
                    continue
                name = (h[345:500].rstrip(b"\0") + b"/" + h[:100].rstrip(b"\0")).decode().strip("/")
                self.found[name] = (off + i + 512, int(h[124:136].strip(b"\0 ") or b"0", 8))
                parts = name.split("/")
                dirs.append(parts[2] if len(parts) > 2 else "")
            self.probes[off] = (dirs[0], dirs[-1]) if dirs else (None, None)
        return self.probes[off]

    def missing(self):
        return [t for t in WANTED if not any(n.endswith(t) for n in self.found)]

    def search(self, lo, hi):
        if not self.missing() or hi - lo <= CHUNK:
            return
        after_lo, before_hi = self.probe(lo)[1], self.probe(hi)[0]
        if after_lo is not None and after_lo == before_hi:
            return
        mid = (lo + hi) // 2 // 512 * 512
        self.probe(mid)
        self.search(lo, mid)
        self.search(mid, hi)

    def locate(self):
        last = max(0, (self.size - CHUNK) // 512 * 512)
        self.search(0, last)
        if self.missing():
            sys.exit(f"could not find {self.missing()}")
        return {t: next(v for n, v in self.found.items() if n.endswith(t)) for t in WANTED}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="+", help="e.g. room1 room2 corridor1")
    ap.add_argument("--out", default="data/clean")
    args = ap.parse_args()

    for seq in args.seq:
        tar = Tar(URL.format(seq))
        dst = Path(args.out) / f"tumvi_{seq}"
        dst.mkdir(parents=True, exist_ok=True)
        for tail, (off, size) in tar.locate().items():
            (dst / WANTED[tail]).write_bytes(tar.read(off, size))
            print(f"{seq}: {tail} ({size >> 10} KB) -> {dst / WANTED[tail]}")
        print(f"{seq}: {len(tar.probes)} requests to find them")


if __name__ == "__main__":
    main()
