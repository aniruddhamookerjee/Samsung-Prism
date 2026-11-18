# Open Questions for Organizers (`prism@samsung.com`)
### Track 3: Path Finder — Working Assumptions & Clarifications

As specified in Workstream C (Robustness and submission), this document records the technical questions sent to the hackathon committee along with the corresponding working assumptions our pipeline is built upon.

---

### Questions & Working Assumptions

| # | Question for Organizers | Our Operational Working Assumption | Technical Rationale & Safeguard in Code |
|---|---|---|---|
| **1** | **Execution Command & Arguments**: Exactly what command line syntax will automated test harness invoke, and how will input/output paths be passed? | `python src/main.py <input_path> [output_path]` | `src/main.py` accepts positional arguments: `$1 = input`, `$2 = output` (defaulting to `estimated_trajectory.txt`). It seamlessly handles direct `.csv`, folder directories, or `.zip` archives. |
| **2** | **Evaluation Target & Output**: Which input file produces the final submitted `estimated_trajectory.txt`? Will evaluation files be run independently by the jury? | We submit the trajectory evaluated on `tumvi_room1` under official degradation. | We document the exact input file in `src/README.md` and generate standard space-separated TUM format. |
| **3** | **Column Ordering in Test Data**: Did organizers apply `degrade_imu.py` to EuRoC column order (`timestamp, gyro, accel`) or default script order (`timestamp, accel, gyro`)? | Handled dynamically for **both** orders. | `clean` includes `gyro_first()`, computing the median $L_2$ norm of column triplets: if the first triplet norm $\approx 9.8\text{ m/s}^2$, it auto-swaps columns to preserve gravity invariants. |
| **4** | **Dropout Burst Duration**: The competition slides suggest dropouts can reach 2 seconds, but `degrade_imu.py` default caps bursts at 50 rows (~0.25s). Can gaps reach 2 seconds? | Yes, gaps can extend to $2.0 \dots 3.5\text{ seconds}$. | Tested on `gaps2s` stress benchmark. The resampler identifies gaps $> 0.3\text{ s}$ and segments gravity alignment without divergence. |
| **5** | **Peak Memory Accounting**: How is the 8.0 MB peak memory measured, and does it include Python runtime / interpreter and library imports? | Measured via `tracemalloc` peak (excluding baseline `import numpy`). | Algorithm buffers utilize only **2.56 MB** peak memory. Even with interpreter and NumPy imports counted, total peak is ~9.5 MB. |
| **6** | **Runtime Limit Scope**: Does the 20.0 ms per 1.0 second of data limit include Python interpreter startup and module import overhead? | Yes, runtime is measured inclusive of execution. | `src/main.py` runs in **3.17 ms per second of data**, providing a 6x safety margin. |
| **7** | **Installed Packages on Evaluation Machines**: Is NumPy available in the test runner? Any other packages allowed? | NumPy only (`numpy>=1.24.0`). | Zero external libraries are imported in `src/main.py` (no pandas, scipy, pyquaternion, etc.). |
| **8** | **Duplicated Input Rows**: When input telemetry contains duplicate rows or non-increasing timestamps, should the output contain duplicate poses for each row? | Yes, exactly one output pose per input row. | Output preserves a 1:1 row count matching input length, with identical timestamp formatting. |
| **9** | **Scoring Formulation**: How are checkpoint accuracy, blind 5 seconds, and dropouts weighted in final scoring? | Rigid alignment (Umeyama $SE(3)$) via `evo` evaluation over full and windowed intervals. | Benchmarked using `tools/score.py` computing ATE, blind-window ATE, gap-window ATE, RPE, and rotation error. |
