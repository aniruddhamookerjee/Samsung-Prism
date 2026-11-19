# Demo Video Script (about 2.5 minutes, never over 3)
## Samsung PRISM XR Hackathon 2026 - Track 3: Path Finder

**Presenter**: Manas Jangid, on behalf of Team SAM
**Format**: screen capture with voiceover: slides, then a live terminal, then the figures.
**Slides**: `presentation/SRMIST_KTR_SAM.pptx` (built by `python tools/make_presentation.py`).

---

### Segment 1: The problem (0:00 - 0:30)
- **Visual**: slide 1 (title), then slide 2 (the problem).
- **Voiceover**:
  > "Hi, we are Team SAM, and this is Path Finder, for Track 3.
  >
  > The task: work out where a device went, in full 3D position and orientation, using nothing but its IMU, the gyroscope and accelerometer. And the data is damaged on purpose: noise that grows, drifting bias, spikes, stuck readings, dropouts of up to two seconds, and for the last five seconds the sensor is dead, all zeros.
  >
  > The usual approach, integrating acceleration twice, falls apart within seconds: one degree of tilt error alone is tens of metres of error within a minute. And it has to run in single-thread Python, in under 8 megabytes, faster than 20 milliseconds per second of data."

---

### Segment 2: The key idea, rotor drag (0:30 - 1:10)
- **Visual**: slide 6 (`docs/figures/drag.png`). Point at the blue and grey lines lying on top of each other.
- **Voiceover**:
  > "Our key idea is a piece of physics most IMU pipelines ignore. On a drone, the thrust points along one body axis. So the accelerometer's other two axes never see gravity or thrust in flight. They see only rotor drag, the air pushing back on the spinning rotors, and that is proportional to the drone's speed.
  >
  > So on a drone, the accelerometer is a speedometer. Here, grey is the true velocity from motion capture, and blue is simply the sideways acceleration divided by minus 0.2, with no integration at all. They match, with a correlation of almost 0.9. Every EuRoC flight fits the same constant.
  >
  > Speed integrated once drifts far less than acceleration integrated twice. On the hardest flight, MH_04, the path error drops from 6.8 to 4.1 metres, and the error in the dead five seconds from 3.9 metres to 0.85.
  >
  > The program switches this on by itself, from the motor vibration it sees in the data, so handheld recordings are not affected."

---

### Segment 3: How the rest works (1:10 - 1:35)
- **Visual**: slide 4 (architecture, seven boxes).
- **Voiceover**:
  > "Around that idea is a seven-stage pipeline in one script. It cleans out spikes, stuck readings, duplicates and bad values. It works out orientation from the gyroscope, with tilt held to gravity. It computes position in the frequency domain, with gains fitted per frequency band against motion-capture ground truth, so real fast motion is kept and slow drift is shrunk. And in the dead five seconds it coasts briefly, then heads back to the take-off point, because these flights land where they took off."

---

### Segment 4: Live run (1:35 - 2:05)
- **Visual**: terminal.
- **Commands**:
  ```bash
  python src/main.py data/degraded/tumvi_room1/imu0/data.csv estimated_trajectory.txt
  python tools/plot_path.py data/degraded/tumvi_room1
  ```
  Then show `results/tumvi_room1.png` (or slide 5).
- **Voiceover**:
  > "Here it is running on the submitted recording, 141 seconds of handheld data. It finishes in about half a second, using under 4 megabytes, well inside both limits. The output has exactly one pose per input row, with every timestamp copied exactly.
  >
  > Blue is our estimate, grey the ground truth. Path error is 0.32 metres, against 1.0 for standing still."

---

### Segment 5: Robustness and close (2:05 - 2:30)
- **Visual**: slide 8 (robustness), then slide 9.
- **Voiceover**:
  > "We tuned on four recordings, then checked on eight more we never tuned on: about two-thirds less error than standing still on the path. And we threw much worse at it than the official damage: double noise, two-second dropouts, files starting mid-flight, sample rates from 50 to 400 hertz, bad values in the file. No crashes, and the output format is right every time.
  >
  > Everything is in our repository: the code, the run guide, Docker, and the scoring tools. Thank you."

---

### Recording checklist
- Run the commands once before recording, so data and figures are in place.
- Use the latest `main` branch; the numbers above match it.
- Keep the terminal font large; hide unrelated windows.
