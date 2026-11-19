# Draft email to the organisers (send from the team lead's address)

**To:** prism@samsung.com
**Subject:** Track 3 (Path Finder): how is the 8 MB peak memory measured?

Hello,

We are Team Prism PathFinders, working on Track 3, Path Finder. We have one question about the resource limits before we submit.

How is the 8 MB peak memory limit measured?

1. Is it the memory our algorithm allocates, for example the `tracemalloc` peak while `main.py` runs, after `import numpy`?
2. Or is it the whole Python process (resident memory), including the interpreter and NumPy itself?

The answer matters because a Python process with NumPy loaded already takes well over 8 MB of resident memory before reading any data, so every NumPy-based Python solution would be over the limit under option 2. Our estimator's own allocations peak at about 3 to 4 MB on the provided recordings (about 10 MB when the Python objects created by `import numpy` are counted too).

Two related questions, if possible:

- Are memory and runtime scored pass/fail against the limits, or ranked (lower is better)?
- Roughly how long is the evaluation recording (a few minutes like the EuRoC and TUM-VI samples, or much longer)?

Thank you,
Team Prism PathFinders
