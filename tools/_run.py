import json
import os
import runpy
import sys
import time
import tracemalloc

mode, script, *args = sys.argv[1:]
sys.argv = [script] + args
sys.path.insert(0, os.path.dirname(os.path.abspath(script)))

base = 0
if mode == "mem":
    tracemalloc.start()
    if "numpy" in open(script, encoding="utf-8").read():
        import numpy  # noqa: F401
    base = tracemalloc.get_traced_memory()[0]
    tracemalloc.reset_peak()

t0 = time.perf_counter()
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit as e:
    if e.code not in (None, 0):
        raise
out = {"seconds": time.perf_counter() - t0}
if mode == "mem":
    out["peak"] = tracemalloc.get_traced_memory()[1]
    out["base"] = base
print("@@" + json.dumps(out), file=sys.stderr)
