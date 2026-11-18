import argparse
import struct
import sys
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from pathlib import Path

BASE = "https://www.research-collection.ethz.ch/server/api/core/bitstreams/{}/content"
BUNDLES = {
    "MH": "7b2419c1-62b5-4714-b7f8-485e5fe3e5fe",
    "V1": "02ecda9a-298f-498b-970c-b7c44334d880",
    "V2": "ea12bc01-3677-4b4c-853d-87c7870b8c44",
}
WANTED = {
    "imu0/data.csv": "imu.csv",
    "state_groundtruth_estimate0/data.csv": "gt.csv",
}
BLOCK = 4 << 20


def http_range(url, lo, hi):
    import ssl
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={
        "Range": f"bytes={lo}-{hi}", "User-Agent": "Mozilla/5.0"})
    for attempt in range(10):
        try:
            return urllib.request.urlopen(req, timeout=300, context=ctx)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503):
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 30 * (attempt + 1)
            print(f"  HTTP {e.code}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("server keeps refusing, try again later")


class HttpFile:
    """Seekable read-only view of a remote file, enough for zipfile to read the index."""

    def __init__(self, url):
        self.url = url
        self.pos = 0
        self.cache = {}
        self.size = int(http_range(url, 0, 0).headers["Content-Range"].split("/")[1])

    def _block(self, i):
        if i not in self.cache:
            lo = i * BLOCK
            self.cache[i] = http_range(self.url, lo, min(lo + BLOCK, self.size) - 1).read()
        return self.cache[i]

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off + (0, self.pos, self.size)[whence]
        return self.pos

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        n = max(0, min(n, self.size - self.pos))
        out = bytearray()
        while len(out) < n:
            i, o = divmod(self.pos, BLOCK)
            chunk = self._block(i)[o:o + n - len(out)]
            out += chunk
            self.pos += len(chunk)
        return bytes(out)


class InflateStream:
    """Forward-only reader over one (possibly deflated) member of the bundle."""

    def __init__(self, resp, deflated, total):
        self.resp = resp
        self.z = zlib.decompressobj(-15) if deflated else None
        self.buf = b""
        self.total = total
        self.got = 0
        self.mark = 0

    def _fill(self):
        raw = self.resp.read(1 << 20)
        if not raw:
            return False
        self.got += len(raw)
        if self.got - self.mark >= 100 << 20:
            self.mark = self.got
            print(f"  {self.got >> 20} / {self.total >> 20} MB", file=sys.stderr)
        self.buf += self.z.decompress(raw) if self.z else raw
        return True

    def read(self, n):
        while len(self.buf) < n and self._fill():
            pass
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def take(self):
        if not self.buf:
            self._fill()
        out, self.buf = self.buf, b""
        return out

    def unread(self, data):
        self.buf = data + self.buf


def walk(stream):
    """Yield (name, bytes or None) for each entry of a zip read front to back."""
    while stream.read(4) == b"PK\x03\x04":
        _, flag, method, _, _, _, csize, _, nlen, elen = struct.unpack("<HHHHHIIIHH", stream.read(26))
        name = stream.read(nlen).decode()
        stream.read(elen)
        keep = any(name.endswith(t) for t in WANTED)
        if flag & 8:
            # sizes come after the data, so the only way to find the end is to inflate it
            z = zlib.decompressobj(-15)
            parts = []
            while not z.eof:
                piece = stream.take()
                if not piece:
                    raise EOFError(name)
                out = z.decompress(piece)
                if keep:
                    parts.append(out)
            stream.unread(z.unused_data)
            stream.read(12 if stream.read(4) == b"PK\x07\x08" else 8)
            data = b"".join(parts)
        else:
            data = stream.read(csize)
            if method == 8 and keep:
                data = zlib.decompress(data, -15)
        yield name, (data if keep else None)


def fetch(seq, out_dir):
    url = BASE.format(BUNDLES[seq.split("_")[0]])
    fp = HttpFile(url)
    bundle = zipfile.ZipFile(fp)
    inner = [n for n in bundle.namelist() if n.endswith(f"{seq}.zip")]
    if not inner:
        sys.exit(f"{seq}: not found in bundle")
    info = bundle.getinfo(inner[0])

    fp.seek(info.header_offset)
    nlen, elen = struct.unpack("<HH", fp.read(30)[26:30])
    start = info.header_offset + 30 + nlen + elen
    resp = http_range(url, start, start + info.compress_size - 1)
    stream = InflateStream(resp, info.compress_type == zipfile.ZIP_DEFLATED, info.compress_size)

    dst = Path(out_dir) / seq
    dst.mkdir(parents=True, exist_ok=True)
    left = dict(WANTED)
    for name, data in walk(stream):
        if data is None:
            continue
        tail = next(t for t in left if name.endswith(t))
        (dst / left.pop(tail)).write_bytes(data)
        print(f"{seq}: {name} -> {dst / WANTED[tail]}")
        if not left:
            break
    resp.close()
    if left:
        sys.exit(f"{seq}: missing {sorted(left)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seq", nargs="*", help="e.g. V1_02_medium V1_03_difficult")
    ap.add_argument("--out", default="data/clean")
    ap.add_argument("--list", choices=sorted(BUNDLES), help="print the bundle's file names and exit")
    args = ap.parse_args()

    if args.list:
        url = BASE.format(BUNDLES[args.list])
        for info in zipfile.ZipFile(HttpFile(url)).infolist():
            print(f"{info.file_size:>12} {info.filename}")
        return
    for seq in args.seq:
        fetch(seq, args.out)


if __name__ == "__main__":
    main()
