# Samsung PRISM XR Hackathon 2026 - Track 3: Path Finder

Estimate a 6-DoF trajectory from a degraded IMU recording only.

## Practice data

Everything under `data/` is generated locally and not committed.

```
pip install -r requirements-dev.txt

# clean IMU + ground truth for two EuRoC recordings
python tools/fetch_euroc.py V1_02_medium V1_03_difficult

# damage them the way the organisers do
python tools/make_degraded.py data/euroc/V1_02_medium/imu.csv data/degraded/V1_02_medium
python tools/make_degraded.py data/euroc/V1_03_difficult/imu.csv data/degraded/V1_03_difficult

# ground truth in TUM format for evo
python tools/gt_to_tum.py data/euroc/V1_02_medium/gt.csv data/euroc/V1_02_medium/gt.tum
python tools/gt_to_tum.py data/euroc/V1_03_difficult/gt.csv data/euroc/V1_03_difficult/gt.tum
```

EuRoC is now hosted as one zip per room (6 to 12 GB) with each recording zipped
again inside it. `fetch_euroc.py` streams a single recording and keeps only the
IMU and ground truth files, so it transfers 0.7 to 1.1 GB per recording but
writes a few MB. Other names: `python tools/fetch_euroc.py --list V1` (also
`MH`, `V2`).

`tools/degrade_imu.py` is the organisers' script, unchanged. It expects
`timestamp, accel, gyro` while EuRoC files are `timestamp, gyro, accel`, so
`make_degraded.py` swaps the columns before and after. `--raw-order` skips the
swap, in case the evaluation files were made that way. `--burst-len 5 400`
gives gaps up to 2 s.

## Scoring

```
python tools/score.py <estimator.py> --label <name>
```

The estimator is run as `python estimator.py <imu csv> <output txt>` on every
recording under `data/degraded`. One row per recording is printed and appended
to `results/results.csv`. Add `--data data/degraded data/degraded_raw` to score
more sets, `--no-save` to leave the table alone.

| column | meaning |
| --- | --- |
| format | `ok`, or what is wrong with the output file (row count, columns, nan, timestamps, quaternion norm) |
| ate_m | position RMSE after rigid alignment, same as `evo_ape tum gt est -a` |
| blind_m | same error, only over the all-zero rows at the end |
| gap_m | same error, from each dropout to 1 s after it |
| rpe_1s_m | drift over 1 s steps |
| rot_deg | orientation RMSE after alignment, same as `evo_ape -a -r angle_deg` |
| ms_per_s | runtime per second of data, imports included, best of 3. Limit 20 |
| mem_mb | tracemalloc peak on top of what `import numpy` already holds. Limit 8 |
| mem_with_imports_mb | tracemalloc peak counting everything |

Notes:

- ate_m and rot_deg agree with evo to 3 decimals on a test path.
- evo accepts files with repeated timestamps, so we keep one pose per input row.
- `evo_ape -a` refuses a path that never moves ("Degenerate covariance rank").
  `score.py` falls back to a shift only, so the stay-still baseline still gets a number.
- `import numpy` alone shows up as about 6.7 MB in tracemalloc. If the organisers
  count imports, 8 MB is not reachable with NumPy, so this is worth asking them.
- EuRoC ground truth starts about 1 s after the IMU file and stops about 1 s
  before it ends, so only 4 of the last 5 blind seconds can be scored.
- With `--raw-order` the script reads the gyro columns as accel in g, so the
  gyro gets about 0.02 rad/s of noise at the end and the accel almost none.

## Layout

```
tools/   data download, degradation, format helpers
data/    local only
results/ results.csv is tracked, the rest is local
```
