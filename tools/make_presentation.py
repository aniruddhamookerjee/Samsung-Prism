#!/usr/bin/env python3
"""Generates the official 9-slide PowerPoint presentation CollegeName_TeamName.pptx."""

from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

def create_deck(output_path="presentation/CollegeName_TeamName.pptx"):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    NAVY = RGBColor(15, 32, 67)
    BLUE = RGBColor(10, 102, 194)
    DARK = RGBColor(33, 37, 41)
    GRAY = RGBColor(108, 117, 125)
    LIGHT_BG = RGBColor(245, 247, 250)
    WHITE = RGBColor(255, 255, 255)

    slides_content = [
        # Slide 1: Title
        {
            "num": "01",
            "title": "Path Finder: 6-DoF Trajectory Estimator",
            "subtitle": "Samsung PRISM XR Hackathon 2026 — Track 3: Path Finder",
            "body": [
                "Robust 6-DoF Inertial Odometry Under Simulated Sensor Jamming & Total Blackout",
                "Authors: Sarthak Singh (Estimator Lead) | Aniruddha Mookerjee (Data/Scoring) | Manas Jangid (Robustness/Submission)",
                "College: CollegeName  |  Team: TeamName",
                "Submission Deadline: 22 November 2026"
            ]
        },
        # Slide 2: The Problem
        {
            "num": "02",
            "title": "The Problem: Inertial Navigation Under Jamming",
            "subtitle": "Mission context and physical sensor challenges",
            "body": [
                "GPS-Denied Flight: Plane navigates solely by dead reckoning through hostile electronic jamming.",
                "Deliberate Multi-Type IMU Damage: Organizers' degrade_imu.py injects growing noise, random walk bias, scale drift, impulse spikes, stuck sensor readings (2-10 samples), dropouts up to 2-3.5s, duplicates, and total blackout in final 5 seconds.",
                "The Drift Dilemma: Plain numerical integration suffers quadratic error explosion (1 deg tilt error = 0.17 m/s² false acceleration = 150m error in 30s).",
                "Strict Contest Constraints: Single-thread Python main.py, <= 8.0 MB peak memory, <= 20 ms / 1s telemetry runtime, exact 1:1 input/output row count matching."
            ]
        },
        # Slide 3: Proposed Solution
        {
            "num": "03",
            "title": "Our Solution: Bounded Frequency-Domain Odometry",
            "subtitle": "Disciplined offline physics vs runaway integration",
            "body": [
                "Offline Global Vision: Exploiting the contest's offline rule to look ahead and behind across the entire flight.",
                "Multi-Tiered Anomaly Cleaning: Fast rejection of duplicate rows, stuck repeats, and adaptive local-noise median spike filtering across all 6 IMU channels.",
                "Gravity-Referenced Attitude Stabilization: Decoupled gyro integration with 30-second rolling gravity-vector projection to permanently lock tilt.",
                "Spectral Bandpass Double Integration: Position estimated via frequency-domain integration (0.02 Hz to 3.0 Hz), eliminating drift while capturing real maneuvers.",
                "Kinematic Coasting Blind Predictor: Exponential velocity coasting (tau=0.6s) blended with return-to-home convergence during sensor blackout."
            ]
        },
        # Slide 4: System Architecture
        {
            "num": "04",
            "title": "End-to-End Pipeline Architecture",
            "subtitle": "7-Stage Lean, Memory-Efficient Processing",
            "body": [
                "1. Read Stream: Streams CSV directly into C-level float arrays via array.array (zero dataframe overhead).",
                "2. Robust Cleaner: Automatically detects column order, dead ending, removes duplicates, stuck samples, and spikes.",
                "3. Resampler: Interpolates valid rows onto uniform 200 Hz grid; segments dropouts longer than 0.3s.",
                "4. Attitude Estimation: Integrates gyro rates; applies 30s rolling gravity alignment to eliminate tilt drift.",
                "5. Position Estimator: Downsamples world-accel to 20 Hz; applies band-pass double integration with 0.25/0.9 horizontal/vertical gain.",
                "6. Blind 5s Predictor: Coasts on last trustworthy velocity, decaying toward origin.",
                "7. Chunked Writer: Streams exactly one normalized pose per input row in 1024-row chunks."
            ]
        },
        # Slide 5: Track Final Output & Verification
        {
            "num": "05",
            "title": "Track Final Output & Verified Benchmarks",
            "subtitle": "Evaluated against ground truth on benchmark tumvi_room1",
            "body": [
                "Format Compliance: estimated_trajectory.txt verified with 27,330 poses (100% 1:1 row match), unit quaternions, 0 NaNs, 0 Infs.",
                "Absolute Trajectory Error (ATE): 0.352 m (Beats Stay-Still baseline of 1.000 m by 65%!).",
                "Dropout Window ATE: 0.385 m (Beats baseline of 0.870 m by 56%).",
                "Blind 5s Window ATE: 0.651 m (Maintains stable trajectory through complete sensor failure).",
                "Relative Pose Error (1s): 0.203 m  |  Rotation Error: 9.719 deg.",
                "Resource Footprint: Peak Memory = 2.56 MB (Limit: 8.0 MB) | Speed = 3.17 ms/s (Limit: 20.0 ms/s)."
            ]
        },
        # Slide 6: Key Differentiators & Technical Innovations
        {
            "num": "06",
            "title": "Key Differentiators & Technical Innovations",
            "subtitle": "Why our approach excels where naive math fails",
            "body": [
                "Frequency-Domain vs Kalman Filter: Conventional EKFs diverge catastrophically when noise covariance changes dynamically under jamming. Spectral integration inherently bounds maximum error.",
                "Asymmetric Gain Scaling: Horizontal motion is kept at 0.25 gain below 0.08 Hz (where tilt error leaks) and 0.9 above, while vertical motion is maintained at 0.9 gain.",
                "Jamming-Adaptive Trust Weighting: Gyro sample-to-sample jitter is monitored continuously; as jamming noise increases, position is smoothly bounded.",
                "Ultra-Lean Memory Footprint: Complete execution operates in 2.56 MB RAM by avoiding pandas/scipy and streaming large files chunk-by-chunk."
            ]
        },
        # Slide 7: Demo & Local Setup Instructions
        {
            "num": "07",
            "title": "Demo & Local Setup Instructions",
            "subtitle": "Zero-configuration reproducibility",
            "body": [
                "Direct Command: python src/main.py <input.csv | folder | zip> [estimated_trajectory.txt]",
                "Docker Execution: docker build -t pathfinder . && docker run --rm -v $(pwd)/data:/data pathfinder /data/input.csv /data/output.txt",
                "Automated Evaluation Suite: python tools/score.py src/main.py --label my_eval",
                "Flexible Inputs: Directly accepts raw CSVs, directories containing imu0/data.csv, or zipped bundles with automated in-memory extraction.",
                "Deterministic: Fixed seeds and robust mathematics ensure identical output on any machine."
            ]
        },
        # Slide 8: Brownie Features & Stress Resilience
        {
            "num": "08",
            "title": "Brownie Features & Stress Resilience",
            "subtitle": "Tested and verified across 7 harsh operational scenarios",
            "body": [
                "Extended 2-Second Dropouts (gaps2s): Successfully maintains track through 2.0-3.5s sensor blackout bursts (ATE: 0.635m).",
                "Double Damage Stress (harsh): Withstands 2.0x maximum organizer noise and bias (ATE: 0.560m).",
                "Column Order Invariance (harsh_raw): Automatically detects and swaps EuRoC vs degradation column orders.",
                "Early Jamming (early, gamma=0.7): Handles early jamming attacks right from initial takeoff.",
                "Edge Case Immunity: Validated with zero crashes on ultra-short recordings (10s, 3s) and tiny 4-row snippets.",
                "Automated Packaging: tools/build_submission.py validates file counts, formats, and generates verified team_name.zip."
            ]
        },
        # Slide 9: Thank You & Team Q&A
        {
            "num": "09",
            "title": "Thank You & Team Q&A",
            "subtitle": "Samsung PRISM XR Hackathon 2026 — Track 3",
            "body": [
                "GitHub Repository: https://github.com/aniruddhamookerjee/Samsung-Prism.git",
                "Active Working Branch: Manas",
                "Organizers Contact: prism@samsung.com",
                "Team Prism PathFinders: Sarthak Singh | Aniruddha Mookerjee | Manas Jangid",
                "We look forward to demonstrating Path Finder to the Samsung Jury on 9 December 2026!"
            ]
        }
    ]

    for data in slides_content:
        slide = prs.slides.add_slide(blank_layout)

        # Header background banner
        header_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(1.5))
        tf = header_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        p0 = tf.paragraphs[0]
        p0.text = f"SLIDE {data['num']}  |  {data['title']}"
        p0.font.size = Pt(24)
        p0.font.bold = True
        p0.font.color.rgb = NAVY

        p1 = tf.add_paragraph()
        p1.text = data['subtitle']
        p1.font.size = Pt(14)
        p1.font.italic = True
        p1.font.color.rgb = BLUE
        p1.space_before = Pt(4)

        # Body content box
        content_box = slide.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(4.8))
        ctf = content_box.text_frame
        ctf.word_wrap = True
        ctf.margin_left = ctf.margin_top = ctf.margin_right = ctf.margin_bottom = 0

        for i, point in enumerate(data['body']):
            p = ctf.paragraphs[0] if i == 0 else ctf.add_paragraph()
            p.text = f"•  {point}"
            p.font.size = Pt(15)
            p.font.color.rgb = DARK
            p.space_before = Pt(12)
            p.line_spacing = 1.15

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_path)
    print(f"Generated presentation: {output_path}")

if __name__ == "__main__":
    create_deck()
