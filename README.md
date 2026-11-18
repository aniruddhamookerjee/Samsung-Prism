# Samsung PRISM XR Hackathon 2026 - Track 3: Path Finder

Estimate a 6-DoF trajectory from a degraded IMU recording only.

## Running the estimator

```
python src/main.py <imu0/data.csv | folder | zip> [estimated_trajectory.txt]
```

Python 3 and NumPy only, single thread. The input can be the csv, a folder that
holds `imu0/data.csv`, or a zip of that folder. The output is TUM format with
exactly one pose per input row and the input timestamps copied digit for digit
(nanoseconds written as seconds). Duplicated input rows get duplicated poses.

### How it works

| step | what it does | why |
| --- | --- | --- |
| read | streams the csv into float32 arrays | memory |
| clean | drops duplicate rows, stuck repeats and spikes (a sample far from the median of its neighbours, scaled by local noise), finds the all-zero ending | the script's damage types |
| resample | valid rows onto a uniform grid, gaps bridged by interpolation, gaps over 0.3 s flagged | dropouts |
| attitude | gyro integrated at full rate with the bias from the first 1.5 s, then the tilt pulled back to gravity using a 30 s average of world acceleration, separately between long gaps | stops tilt drift without erasing real motion |
| position | world acceleration averaged to 20 Hz, gravity removed, double-integrated in the frequency domain inside a band-pass | slow drift from bias and tilt error never builds up |
| shrink | horizontal gain 0.25 below 0.08 Hz and 0.9 above, height gain 0.3; position faded towards zero where the gyro is mostly noise | a path that is too big costs more than one that is too small |
| blind 5 s | coast for a moment on the last velocity, then head for the estimated start point | every practice recording ends within 0.45 m of where it began |
| write | poses interpolated onto every input timestamp, 1024 rows at a time | memory |

The idea behind the shrink: with an IMU alone, slow horizontal motion cannot be
told apart from a small tilt error (1 degree of tilt is 0.17 m/s^2 of false
acceleration, metres of error within half a minute). Fast motion and height are
much better. So the estimate keeps fast motion at almost full size and slow
horizontal motion at a quarter, and never lets drift accumulate.

### Results (sarthak-v2, metres)

| recording | stay-still ate | ours ate | stay-still blind | ours blind |
| --- | --- | --- | --- | --- |
| V1_02_medium | 1.78 | 1.24 | 1.04 | 1.06 |
| V1_03_difficult | 1.58 | 1.36 | 1.27 | 1.38 |
| MH_04_difficult | 6.81 | 6.50 | 3.85 | 3.83 |
| tumvi_room1 | 1.00 | 0.36 | 0.63 | 0.62 |

Across the default, raw-order and four harsher stress sets (20 runs), the path
error is 22% below stay-still on average and below it in every run. Peak memory
is 2.7 to 3.5 MB (tracemalloc, after `import numpy`), runtime 1.4 to 2 ms per
second of data. Full rows are in `results/results.csv`.

Known limits:

- The blind 5 s is about as good as stay-still: 0.98 of it on average over 24
  runs, worst 1.04. Holding the true last position would be 3 to 15 times
  better, but an IMU alone cannot place the end of the path that well, and
  plain integration from the still start is already 0.5 to 3 m off after 10 s.
- A 3 s file takes about 30 ms per second, nearly all of it the NumPy import.
- About 2 MB of tracemalloc peak is Python compiling the script itself, on any input.
- Tuning: `python tools/tune.py key=value ...` scores settings in-process.

## Practice data

Everything under `data/` is generated locally and not committed.

```
pip install -r requirements-dev.txt

# clean IMU + ground truth, written to data/clean/<name>/
python tools/fetch_euroc.py V1_02_medium V1_03_difficult MH_04_difficult
python tools/fetch_tumvi.py room1

# ground truth in TUM format, plus the damaged copies in data/degraded and data/degraded_raw
python tools/prepare_data.py
```

EuRoC is now hosted as one zip per room (6 to 12 GB) with each recording zipped
again inside it. `fetch_euroc.py` streams a single recording and keeps only the
IMU and ground truth files, so it transfers 0.7 to 1.1 GB per recording but
writes a few MB. Other names: `python tools/fetch_euroc.py --list V1` (also
`MH`, `V2`).

TUM-VI recordings are plain tar files, so `fetch_tumvi.py` finds the two csv
files with a handful of range requests and downloads about 5 MB.

`tools/degrade_imu.py` is the organisers' script, unchanged. It expects
`timestamp, accel, gyro` while EuRoC files are `timestamp, gyro, accel`, so
`make_degraded.py` swaps the columns before and after. `--raw-order` skips the
swap, in case the evaluation files were made that way. `prepare_data.py` makes
both. For a single file with other settings use `make_degraded.py` directly,
e.g. `--burst-len 5 400` for gaps up to 2 s.

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

Stay-still baseline, the numbers to beat (metres):

| recording | length | ate_m | blind_m | gap_m |
| --- | --- | --- | --- | --- |
| V1_02_medium | 85 s | 1.78 | 1.04 | 1.61 |
| V1_03_difficult | 107 s | 1.58 | 1.27 | 1.09 |
| MH_04_difficult | 102 s | 6.81 | 3.85 | 7.87 |
| tumvi_room1 | 141 s | 1.00 | 0.63 | 0.87 |

Every scored version is in `results/results.csv`.

## Stress sets

```
python tools/prepare_data.py --stress
python tools/score.py <estimator.py> --label <name> --stress
```

| set | what changes |
| --- | --- |
| gaps2s | bursts up to 400 rows and twice as often, longest gap 2.0 to 3.5 s |
| harsh | damage level 2.0, twice the organisers' maximum |
| early | gamma 0.7, so the damage arrives early instead of at the end |
| harsh_raw | harsh, with the script fed EuRoC column order |
| short10 | first 10 s only, half of it is the all-zero ending |
| short3 | first 3 s only, too short for the script to add a zero ending |
| tiny | 4 or 5 rows |

An estimator that crashes, hangs (`--timeout`, 120 s by default) or writes a bad
file gets a row saying so in the `format` column and the run carries on.

What the two reference estimators showed:

- Neither crashes or writes a bad file on any set.
- Stay-still error barely moves with the damage (it ignores the data), so these
  sets only tell us something once a real estimator is scored on them.
- Fixed start-up cost matters on short files. Stay-still spends 0.6 ms/s on a
  full recording but 8 ms/s on a 3 s file, with no NumPy import at all. If the
  evaluation file is short, a 100 to 150 ms NumPy import alone could use most
  of the 20 ms/s.
- Plain integration is 18 m off after 10 s and 0.5 to 0.9 m off after 3 s.
- Both Vicon Room recordings start with the drone still for the first few
  seconds, which is what the 2 s calibration window needs.

Notes:

- ate_m and rot_deg agree with evo to 3 decimals on a test path.
- evo accepts files with repeated timestamps, so we keep one pose per input row.
- `evo_ape -a` refuses a path that never moves ("Degenerate covariance rank").
  `score.py` falls back to a shift only, so the stay-still baseline still gets a number.
- `import numpy` alone shows up as about 6.7 MB in tracemalloc. If the organisers
  count imports, 8 MB is not reachable with NumPy, so this is worth asking them.
- `tools/naive_integrate.py` is plain integration with no bias handling, kept as
  a reference. It ends up kilometres off, so stay-still is the real bar. It also
  holds every row as Python floats and already uses 6 to 10 MB doing so.
- EuRoC ground truth starts about 1 s after the IMU file and stops about 1 s
  before it ends, so only 4 of the last 5 blind seconds can be scored.
- With `--raw-order` the script reads the gyro columns as accel in g, so the
  gyro gets about 0.02 rad/s of noise at the end and the accel almost none.

## Layout

```
tools/   data download, degradation, scoring
data/    local only
results/ results.csv is tracked, the rest is local
```
