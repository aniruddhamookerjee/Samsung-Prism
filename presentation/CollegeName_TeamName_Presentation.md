# Samsung PRISM XR Hackathon 2026 - Track 3: Path Finder
## 9-Slide Official Presentation Deck: `CollegeName_TeamName`

---

### Slide 1: Title
- **Headline**: Path Finder: 6-DoF Trajectory Estimation Under Heavy IMU Degradation
- **Subtitle**: Samsung PRISM XR Hackathon 2026 — Track 3
- **Team**: Team Prism PathFinders
  - *Sarthak Singh* (Lead, Estimator Core)
  - *Aniruddha Mookerjee* (Data, Degradation & Benchmark Harness)
  - *Manas Jangid* (Robustness, Blind Predictor, Packaging & Submission)
- **Institution**: CollegeName
- **Submission Date**: November 2026

---

### Slide 2: The Problem
- **Mission Context**: An autonomous aircraft flies a critical reconnaissance mission through GPS-denied airspace. Electronic warfare jamming deliberately degrades IMU sensor telemetry over time, culminating in total sensor blackout for the final 5 seconds.
- **Sensor Constraints**:
  - Only raw 6-DoF IMU data (`timestamp, gyro, accel`) — no vision, no GPS, no magnetometers, no map priors.
  - Complex degradation profile: non-linear noise ramp ($\gamma = 1.7$), random-walk bias drift, scale errors, impulse spikes, stuck sensor readings (2–10 frames), burst dropouts (up to 2–3.5s), duplicated rows, and trailing total sensor blackout.
- **Strict Hackathon Hard Limits**:
  - Memory: Peak memory $\le 8\text{ MB}$ (no pandas/scipy).
  - Runtime: $\le 20\text{ ms}$ per 1 second of telemetry on a single CPU thread.
  - File Contract: Exact 1:1 row count and timestamps in TUM format; no crashes on extreme edge cases.

---

### Slide 3: Proposed Solution
- **Core Philosophy**: A disciplined, offline, frequency-bounded inertial estimator that rejects unobservable low-frequency drift before it compounds into quadratic runaway error.
- **Key Tenets**:
  1. **Strict Memory & Speed Budgeting**: Raw C-level streaming buffers (`array.array`), single-threaded NumPy math, chunked file I/O ($< 3\text{ MB}$ peak allocation, $\sim 2.1\text{ ms/s}$ runtime).
  2. **Multi-Stage Anomaly Filtering**: Real-time rejection of duplicate timestamps, stuck sensor states, and 6-channel adaptive local noise spike trimming.
  3. **Decoupled Orientation & Offline Tilt Locking**: Quiescent bias estimation combined with a 30s rolling gravity-vector projection to eliminate pitch/roll tilt drift.
  4. **Band-Pass Spectral Integration**: Double integration performed in frequency domain ($0.02\text{ Hz} \dots 3.0\text{ Hz}$) with asymmetric horizontal/vertical attenuation.
  5. **Rotor-Drag Velocity Sensing**: On a drone, the accelerometer axes across the thrust read $-0.2 \times$ velocity, so slow horizontal motion is measured, not double-integrated.
  6. **Kinematic Coasting Blind Predictor**: Decaying velocity coasting coupled with mission return attraction during the final 5-second blackout.

---

### Slide 4: System Architecture
- **7-Stage Linear Pipeline**:
  ```
  [Raw Input: CSV / Zip / Folder]
               │
               ▼
   1. Stream Reader (array.array C-buffers, 0 memory waste)
               │
               ▼
   2. Robust Cleaner (drops dups, stuck repeats, spikes, detects dead window)
               │
               ▼
   3. Resampler (uniform 200 Hz grid, dropout gap tracking > 0.3s)
               │
               ▼
   4. Attitude Filter (quaternion rate integration + 30s gravity tilt alignment)
               │
               ▼
   5. Position Estimator (block world-acceleration + FFT bandpass integration)
               │
               ▼
   6. Blind 5s Predictor (exponential velocity decay + origin attraction)
               │
               ▼
   7. Chunked TUM Writer (interpolates poses onto original input timestamps)
               │
               ▼
   [estimated_trajectory.txt]
  ```

---

### Slide 5: Track Final Output & Verification
- **Output Artifact**: `estimated_trajectory.txt`
  - Compliant with TUM format: `timestamp tx ty tz qx qy qz qw`
  - Evaluated on benchmark `tumvi_room1`: 27,330 rows, exactly matching input count and timestamps.
  - Quaternion normalization verified: $\|q\| = 1.0 \pm 10^{-7}$; 0 NaNs, 0 Infs.
- **Scored Results vs Stay-Still Baseline**:
  - **Absolute Trajectory Error (ATE)**: **0.318 m** vs 1.000 m baseline (**68% error reduction!**)
  - **Dropout Gap Window ATE**: **0.331 m** vs 0.869 m baseline (**62% error reduction!**)
  - **Relative Pose Error (RPE 1s)**: **0.194 m**
  - **Rotation Error**: **9.732°** across the entire 141-second trajectory.
  - **Peak Memory**: **3.06 MB** (Budget: 8.0 MB — utilizing only 38% of allowed memory).
  - **Processing Speed**: **2.17 ms/s** (Budget: 20.0 ms/s — **9.2x faster than required limit**).
- **Across all drone and handheld runs**: path error 0.62x and blind 5 s error 0.58x of stay-still over 24 tuning runs; 0.68x path over 15 held-out runs and 0.64x over 10 runs on five recordings never used for tuning.
- **Figure for this slide**: `docs/figures/drag.png` (accelerometer-derived velocity vs motion-capture velocity) and `docs/figures/MH_04_difficult.png` (path vs ground truth).

---

### Slide 6: Key Differentiators & Technical Innovations
1. **Rotor Drag as a Velocity Sensor (our key idea)**: A multirotor's thrust is along one body axis, so the other two accelerometer axes see only rotor drag, $a = -k\,v$. Against ground truth every EuRoC flight fits the same $k = 0.18 \dots 0.22\text{ s}^{-1}$ (correlation up to 0.98). Velocity integrated once drifts far less than acceleration integrated twice. Drag is read perpendicular to the measured thrust direction (the EuRoC IMU is mounted 20 deg off it), and the velocity is zero where motor vibration drops to idle (drone on the pad). MH_04 path error 6.50 m to 4.07 m, blind 5 s error 3.67 m to 0.85 m (the blind 5 s on all four practice flights: 0.58x stay-still). Slow motion below 0.02 Hz is kept through a second-order high pass rather than cut off. Detected automatically from motor vibration, so handheld data is untouched.
2. **Frequency-Domain Double Integration**: Traditional time-domain Riemann integration ($\iint a\,dt^2$) quadratically explodes with any minute tilt bias ($1^\circ \text{ tilt} \to 0.17\text{ m/s}^2 \to 150\text{ m}$ drift in 30s). Our spectral integration filters out the DC drift band while preserving dynamic maneuvers.
3. **Asymmetric Gain Optimization**: Recognizes that horizontal acceleration is highly sensitive to tilt errors, whereas vertical acceleration is bounded by gravity. Gains are fitted per frequency band against motion-capture ground truth: slow horizontal motion (below 0.065 Hz) kept at $0.15$, faster motion at $1.0$, preventing false lateral wander.
4. **Adaptive Gyro Jamming Trust Weighting**: Dynamically computes sample-to-sample jitter $\Delta\omega$; as jamming intensifies, position confidence automatically fades toward safe bounds.
5. **Zero-Overhead Memory Layout**: Eliminates heavy dataframes (pandas) in favor of Python's built-in `array` and float32 block buffers, ensuring complete execution well below 4 MB.

---

### Slide 7: Demo & Local Setup Instructions
- **Single Command Run**:
  ```bash
  python src/main.py data/degraded/tumvi_room1/imu0/data.csv estimated_trajectory.txt
  ```
- **Dockerized Execution**:
  ```bash
  docker build -t pathfinder .
  docker run --rm -v ${PWD}/data:/data pathfinder /data/degraded/imu0/data.csv /data/output.txt
  ```
- **Automated Scoring Suite**:
  ```bash
  python tools/score.py src/main.py --label submission_test
  ```
- **Zero-Config Inputs**: Supports direct CSV paths, folders containing `imu0/data.csv`, and zipped archives.

---

### Slide 8: Brownie Features & Stress Resilience
- **Comprehensive Stress Test Suite Tested & Validated**:
  - **2-Second Extended Dropouts (`gaps2s`)**: Successfully bridges multi-second packet loss without state desync (ATE: 0.635 m).
  - **2.0x Double Damage (`harsh`)**: Withstands double the organizers' noise and bias degradation (ATE: 0.560 m).
  - **Inverted Column Order (`harsh_raw`)**: Auto-identifies whether gyro or accel appears first by inspecting gravitational norms.
  - **Early Jamming Ramp (`early`, $\gamma = 0.7$)**: Operates cleanly when jamming occurs immediately at takeoff.
  - **Edge Cases**: Zero crashes on ultra-short recordings (10s, 3s) and 4-row tiny files.
- **Automated Submission Builder**: One-step creation of verified `team_name.zip` with automated checksum and format validation.

---

### Slide 9: Thank You & Q&A
- **Repository**: [https://github.com/aniruddhamookerjee/Samsung-Prism.git](https://github.com/aniruddhamookerjee/Samsung-Prism.git)
- **Branch**: `Manas`
- **Contact & Clarifications**: Sent to `prism@samsung.com`
- **Team Prism PathFinders**:
  - *Sarthak Singh* | *Aniruddha Mookerjee* | *Manas Jangid*
- Ready for Final Samsung Jury Demo on December 9, 2026!
