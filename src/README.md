# Track 3: Path Finder - Trajectory Estimator

A standalone, high-performance, single-threaded Python pipeline to estimate full 6-DoF trajectories (`timestamp tx ty tz qx qy qz qw`) from heavily degraded IMU telemetry under simulated GPS jamming and sensor degradation.

Designed for the **Samsung PRISM XR Hackathon 2026 (Track 3: Path Finder)**.

---

## 1. Quick Start & Execution

### Requirements
- Python 3.10+
- `numpy>=1.24.0`
- Strictly single-threaded, zero heavy dependencies (no pandas, scipy, or torch at runtime).

### Usage

```bash
# Standard usage (writes to estimated_trajectory.txt by default)
python src/main.py <input_path> [output_path]
```

### Supported Input Types
`src/main.py` automatically detects and processes:
1. **Direct CSV file**: `python src/main.py imu0/data.csv estimated_trajectory.txt`
2. **Directory**: `python src/main.py path/to/recording_folder/ estimated_trajectory.txt` (searches for `imu0/data.csv` or `data.csv`)
3. **Zipped Archive**: `python src/main.py recording.zip estimated_trajectory.txt` (streams internal csv without extracting full archive to disk)

---

## 2. Benchmark Compliance & Constraints

| Metric | Hackathon Limit | Our Performance (`tumvi_room1`) | Status |
| :--- | :--- | :--- | :--- |
| **Language** | Python only (`main.py`) | Pure Python + NumPy | **PASS (100%)** |
| **Peak Memory** | `< 8.0 MB` (tracemalloc) | **3.83 MB** (algorithm buffers) | **PASS (< 50% of budget)** |
| **Execution Speed** | `< 20.0 ms / 1 s data` | **3.42 ms / 1 s data** | **PASS (about 6x under the limit)** |
| **Parallelism** | Single thread only | Strictly single thread | **PASS** |
| **Output Integrity** | Exact 1:1 row count & timestamps | 27,330 / 27,330 exact match | **PASS** |
| **Alignment Score (ATE)**| Baseline: 1.00 m | **0.318 m** (0.32x baseline error) | **EXCEEDS BASELINE** |
| **Blind 5s Window ATE** | Baseline: 0.63 m | **0.603 m** | **BEATS BASELINE** |

---

## 3. Architecture & Algorithmic Pipeline

The estimator processes telemetry offline in seven sequential stages:

```
[Degraded IMU Stream]
         │
         ▼
 1. Stream Reader (array.array C-buffers; zero memory waste)
         │
         ▼
 2. Robust Cleaner (drops duplicate rows, stuck repeats, adapts to spikes & detects dead window)
         │
         ▼
 3. Resampler (uniform 200 Hz time grid; flags long dropout bursts > 0.3s)
         │
         ▼
 4. Attitude Estimation (quaternion integration + 30s rolling gravity vector tilt alignment)
         │
         ▼
 5. Position Estimation (block world-acceleration + bandpass double integration 0.02 - 3.0 Hz)
         │
         ▼
 6. Blind 5-Second Predictor (damped exponential velocity coasting + home-point attraction)
         │
         ▼
 7. Chunked Writer (interpolates poses onto original input timestamps in 1024-row blocks)
         │
         ▼
[estimated_trajectory.txt]
```

### Detailed Stage Breakdown:

1. **`read_imu`**: Streams raw CSV into contiguous `array('q')` (64-bit timestamps) and `array('f')` (32-bit sensor readings). Timestamp fractions in seconds are converted to integer nanoseconds using exact string arithmetic, avoiding IEEE 754 precision drift.
2. **`clean`**:
   - **Total Failure (Blind Window)**: Detects trailing all-zero rows where sensor power failed.
   - **Bad Values**: Rows holding `nan` or `inf` are dropped like any other missing sample (one such value would otherwise poison the whole trajectory).
   - **Stuck Samples & Duplicates**: Rejects repeated identical sensor readings ($2 \dots 10$ samples) and duplicate or backward timestamps.
   - **Spike Rejection**: 3-point median filter with rolling local noise estimator. Rejects impulse spikes exceeding $8 \times \sigma_{\text{local}} + \text{threshold}$.
   - **Column Order Invariance**: Automatically detects whether input is EuRoC order (`gyro, accel`) or degradation script order (`accel, gyro`) by evaluating gravitational norms ($|\mathbf{a}| \approx 9.8\text{ m/s}^2$).
3. **`resample`**: Interpolates non-uniform timestamps across short gaps onto a steady sampling rate ($f_s \approx 200\text{ Hz}$). Dropout bursts exceeding $0.3\text{ s}$ are marked as unmeasured gaps.
4. **`attitude`**:
   - Computes initial gyro bias in a quiescent calibration window ($t \le 2.0\text{ s}$).
   - With no still start (a file that begins mid-flight), fits the gyro bias from how fast the tilt drifts away from gravity, and keeps it only if the fit settles on a plausible value.
   - Integrates angular rates using single-precision unit quaternions.
   - Computes offline tilt correction by observing that the average low-frequency world acceleration vector over $30\text{ s}$ aligns strictly with gravity ($+1g$ vertical).
5. **`position`**:
   - Downsamples world acceleration to $20\text{ Hz}$ to drastically cut FFT memory and compute overhead.
   - Performs frequency-domain double integration within a tuned pass band (horizontal from $0.03\text{ Hz}$, vertical from $0.02\text{ Hz}$, up to $3.0\text{ Hz}$).
   - Employs asymmetric gain scaling ($0.15$ horizontal below $0.065\text{ Hz}$, $1.0$ above) to penalize false horizontal acceleration induced by residual tilt errors.
   - Attenuates position variance when high-frequency gyro noise indicates heavy sensor jamming.
   - **Rotor-drag velocity (multirotors)**: when the accelerometer carries motor vibration, the two directions perpendicular to the measured thrust direction (the EuRoC IMU is mounted about 20 deg off it) measure only rotor drag, $a = -k\,v$ with $k \approx 0.2\text{ s}^{-1}$ (fitted 0.18 to 0.22 on every EuRoC flight against ground truth). Below $0.08\text{ Hz}$, horizontal position comes from integrating this directly measured velocity once instead of acceleration twice. Where the motor vibration drops below 0.6 of its typical level the drone is on the ground, and the velocity is set to zero. Handheld recordings have no motor vibration and skip this step. The side-axis offsets are solved so that the mean velocity in the room is zero, slow motion below $0.02\text{ Hz}$ fades in through a second-order high pass ($f^2/(f^2+f_c^2)$, $f_c = 0.015\text{ Hz}$, gain 0.7) instead of being cut off, and on the ground the height is held at one floor level.
6. **`blind` 5-Second Prediction**:
   - When the sensor dies, initial velocity is computed over the preceding $0.5\text{ s}$.
   - Trajectory smoothly coasts with velocity exponential decay ($\tau = 0.3\text{ s}$) while gently returning towards the launch/home position, averaged over the first $12\text{ s}$ ($\tau = 1.0\text{ s}$): the practice flights land where they took off. On a drone the target height is the floor level measured on the ground stretches (in the ground truth every practice flight ends within about $0.15\text{ m}$ of its take-off height).
7. **`write`**:
   - Evaluates poses at the exact input timestamps and streams 8 space-separated columns in 1024-row chunks, so writing never holds the whole output in memory.

---

## 4. Submitted Trajectory File

- **File**: `estimated_trajectory.txt` (included in repository root and submission bundle)
- **Input Source**: `data/degraded/tumvi_room1/imu0/data.csv`
- **Output Characteristics**:
  - Total poses: **27,330** (exact 1:1 match with input rows)
  - Columns: `timestamp tx ty tz qx qy qz qw`
  - Normalization: $\|q\| = 1.0 \pm 10^{-7}$
  - Invalid values: 0 NaN, 0 Inf

---

## 5. Working Assumptions & Technical Specifications

| # | Question / Scenario | Hackathon Working Assumption | Implementation Details |
|---|---|---|---|
| 1 | **Command Line Syntax** | `python src/main.py <input> <output>` | Fully supported, with default output fallback to `estimated_trajectory.txt`. |
| 2 | **Input Archive Packaging** | Folder or `.zip` file | Built-in streaming zipfile extraction without disk inflation. |
| 3 | **Sensor Column Order** | EuRoC (`gyro, accel`) vs Script (`accel, gyro`) | Auto-detected using gravity norm heuristics ($g \approx 9.81$). |
| 4 | **Dropout Window Duration** | Gaps up to $2.0 \dots 3.5\text{ s}$ | Resampler tracks gap boundaries; skips acceleration integration across unmeasured voids. |
| 5 | **Memory Measurement** | Peak Python `tracemalloc`, without what `import numpy` holds (FAQ: algorithm / heap level) | 2.8 to 5.3 MB on every practice and stress run. Counting the NumPy import it is 9.5 to 12 MB. |
| 6 | **Duplicates & Jitter** | Identical rows & timestamps | Handled gracefully: output preserves duplicate poses corresponding to repeated input rows. |
| 7 | **Sensor Total Failure** | Trailing $5\text{ s}$ all-zeros | Detected dynamically; dead-reckoning state transitions to blind coasting. |
