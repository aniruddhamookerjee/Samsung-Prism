# Demo Video Walkthrough Script (2 to 3 Minutes)
## Samsung PRISM XR Hackathon 2026 - Track 3: Path Finder

**Target Duration**: 2 minutes 30 seconds (Strict limit: Never exceed 3 minutes)  
**Presenter**: Workstream C (Manas Jangid) on behalf of Team Prism PathFinders  
**Format**: Screen capture with voiceover and live terminal demonstration

---

### Segment 1: Introduction & Mission Context (0:00 - 0:35)
- **Visual**: Show Title Slide / Architecture diagram.
- **Voiceover**:
  > "Hello everyone, welcome to our presentation and demonstration of **Track 3: Path Finder** for the Samsung PRISM XR Hackathon 2026.
  > 
  > In this challenge, our task is to reconstruct the full 6-DoF trajectory of an aircraft flying through GPS-denied airspace. An adversary is deploying intense electronic jamming against the aircraft's onboard IMU sensor. Over the course of the flight, noise intensifies, sensor bias drifts, sample dropouts and spikes occur, and for the final 5 seconds, the sensor dies completely into total blackout.
  > 
  > With no external cameras, GPS, or ground checkpoints, naive numerical integration diverges quadratically within seconds. Furthermore, we must strictly respect the competition's hard limits: pure Python, single thread, under 8 MB of RAM, and under 20 ms per second of telemetry."

---

### Segment 2: Pipeline Architecture & Technical Innovations (0:35 - 1:20)
- **Visual**: Show diagram of the 7-stage pipeline (`read -> clean -> resample -> attitude -> position -> blind -> write`).
- **Voiceover**:
  > "To solve this without letting drift explode, we built a 7-stage streaming pipeline inside a single standalone script:
  > 
  > 1. **Zero-Overhead Ingestion**: We stream the CSV directly into contiguous C-level float arrays via Python's standard `array` module, bypassing heavy DataFrame allocations.
  > 2. **Multi-Type Anomaly Cleaning**: We automatically detect sensor column order, strip stuck samples, prune duplicate timestamps, and apply an adaptive median spike filter across all 6 channels.
  > 3. **Decoupled Attitude & Gravity Lock**: We integrate angular rates into unit quaternions and project against a 30-second rolling gravity vector to permanently eliminate pitch and roll tilt drift.
  > 4. **Spectral Band-Pass Integration**: Instead of accumulating DC bias, we perform double integration in the frequency domain between 0.02 Hz and 3.0 Hz, with 0.25 horizontal gain and 0.90 vertical gain to preserve genuine flight maneuvers.
  > 5. **Physics-Based Blind Prediction**: When sensor telemetry flatlines to zero, our blind predictor smoothly coasts on the last reliable velocity while gently returning towards the launch origin."

---

### Segment 3: Live Terminal Demo & Performance Metrics (1:20 - 2:05)
- **Visual**: Live terminal window showing execution of `src/main.py` and `tools/score.py`.
- **Command Executed**:
  ```bash
  python src/main.py data/degraded/tumvi_room1/imu0/data.csv estimated_trajectory.txt
  python tools/score.py src/main.py --label live_demo
  ```
- **Voiceover**:
  > "Let's see it in action. We execute `src/main.py` on the degraded `tumvi_room1` sequence. Notice the speed: the entire 141-second trajectory processes in less than half a second.
  > 
  > Now let's examine the official scoring tool output:
  > - **Format**: 100% OK, exactly matching all 27,330 input rows and timestamps.
  > - **Absolute Trajectory Error (ATE)**: **0.352 meters**, beating the stay-still benchmark of 1.000 meter by 65%.
  > - **Blind Window Error**: **0.651 meters**, demonstrating tight tracking even during total blackout.
  > - **Processing Speed**: **3.17 ms per second of data**, over 6 times faster than the 20 ms limit!
  > - **Peak Memory**: Just **2.56 MB**, using barely a third of the allowed 8 MB budget!"

---

### Segment 4: Stress Resilience & Conclusion (2:05 - 2:30)
- **Visual**: Show stress test results table and GitHub repository / packaging overview.
- **Voiceover**:
  > "Beyond the standard dataset, our pipeline has been hardened across 7 extreme stress suites—including 2-second packet bursts, double damage levels, inverted column orders, and tiny 4-row snippets—with zero crashes and zero format faults.
  > 
  > All deliverables, including `src/main.py`, the exact run guide in `src/README.md`, our verified `estimated_trajectory.txt`, `metadata.json`, `Dockerfile`, and the presentation deck, are packaged and verified.
  > 
  > Thank you, and we look forward to meeting the Samsung jury on December 9th!"
