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

## Scoring with evo

```
python tools/stay_still.py data/degraded/V1_02_medium/imu0/data.csv results/still.txt
evo_ape tum data/euroc/V1_02_medium/gt.tum results/still.txt -a
```

Notes from the first runs:

- evo accepts files with repeated timestamps, so we keep one pose per input row.
- `evo_ape -a` refuses a path that never moves ("Degenerate covariance rank").
  The stay-still baseline has to be scored without evo's alignment.

## Layout

```
tools/   data download, degradation, format helpers
data/    local only
results/ local only
```
