"""Builds the 9-slide deck presentation/CollegeName_TeamName.pptx.

    pip install python-pptx
    python tools/make_presentation.py

The tumvi_room1 numbers are read from metadata.json, the figures from
docs/figures (redraw them with tools/plot_drag.py and tools/plot_path.py).
Set COLLEGE and TEAM below before the final build.
"""

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

COLLEGE = "CollegeName"          # <- fill in
TEAM = "Team Prism PathFinders"
MEMBERS = [("Sarthak Singh", "Lead, estimator core"),
           ("Aniruddha Mookerjee", "Data, degradation and scoring"),
           ("Manas Jangid", "Robustness, packaging and submission")]
REPO = "https://github.com/aniruddhamookerjee/Samsung-Prism"

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "docs" / "figures"

NAVY = RGBColor(0x14, 0x2A, 0x4F)
BLUE = RGBColor(0x1F, 0x6F, 0xD1)
ORANGE = RGBColor(0xD1, 0x49, 0x1F)
DARK = RGBColor(0x22, 0x22, 0x22)
GREY = RGBColor(0x66, 0x66, 0x66)
LIGHT = RGBColor(0xEE, 0xF3, 0xFA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

W, H = Inches(13.333), Inches(7.5)


def text(slide, x, y, w, h, lines, size=16, color=DARK, bold=False, align=None, anchor=None, font=None):
    """lines: str or list of str / (str, dict) with per-line overrides."""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    if anchor:
        tf.vertical_anchor = anchor
    if isinstance(lines, str):
        lines = [lines]
    for i, ln in enumerate(lines):
        opt = {}
        if isinstance(ln, tuple):
            ln, opt = ln
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = ln
        if opt.get("mono") or font:
            r.font.name = "Consolas"
        r.font.size = Pt(opt.get("size", size))
        r.font.bold = opt.get("bold", bold)
        r.font.color.rgb = opt.get("color", color)
        p.space_before = Pt(opt.get("before", 6 if i else 0))
        if align or opt.get("align"):
            p.alignment = opt.get("align", align)
    return box


def bullets(slide, x, y, w, h, items, size=16):
    lines = []
    for it in items:
        if isinstance(it, tuple):          # (bold lead, rest)
            lines.append(it)
        else:
            lines.append((None, it))
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    for i, (lead, rest) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(0 if i == 0 else 10)
        r = p.add_run()
        r.text = "▪  "
        r.font.size = Pt(size)
        r.font.color.rgb = BLUE
        if lead:
            r = p.add_run()
            r.text = lead + " "
            r.font.size = Pt(size)
            r.font.bold = True
            r.font.color.rgb = NAVY
        r = p.add_run()
        r.text = rest
        r.font.size = Pt(size)
        r.font.color.rgb = DARK
    return box


def header(slide, num, title, sub=None):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Inches(0.12))
    bar.fill.solid()
    bar.fill.fore_color.rgb = BLUE
    bar.line.fill.background()
    text(slide, Inches(0.6), Inches(0.35), Inches(11.5), Inches(0.7), title, size=30, color=NAVY, bold=True)
    if sub:
        text(slide, Inches(0.6), Inches(1.0), Inches(11.5), Inches(0.5), sub, size=16, color=GREY)
    text(slide, Inches(11.9), Inches(7.0), Inches(1.2), Inches(0.35), f"{num} / 9", size=11, color=GREY,
         align=PP_ALIGN.RIGHT)
    text(slide, Inches(0.6), Inches(7.0), Inches(8), Inches(0.35),
         f"Path Finder  |  {TEAM}  |  Samsung PRISM XR Hackathon 2026, Track 3", size=11, color=GREY)


def picture(slide, name, x, y, w=None, h=None):
    p = FIG / name
    if p.exists():
        return slide.shapes.add_picture(str(p), x, y, width=w, height=h)
    text(slide, x, y, w or Inches(4), Inches(0.5), f"[missing figure {name}]", color=ORANGE)


def table(slide, x, y, w, rows, col_w, size=14, highlight_col=None):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, Inches(0.42 * len(rows)))
    t = shape.table
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.text = str(val)
            p = c.text_frame.paragraphs[0]
            p.font.size = Pt(size)
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            if i == 0:
                c.fill.fore_color.rgb = NAVY
                p.font.color.rgb = WHITE
                p.font.bold = True
            else:
                c.fill.fore_color.rgb = LIGHT if i % 2 else WHITE
                p.font.color.rgb = DARK
                if highlight_col is not None and j == highlight_col:
                    p.font.bold = True
                    p.font.color.rgb = BLUE
    return shape


def create_deck(output_path=ROOT / "presentation" / "CollegeName_TeamName.pptx"):
    meta = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    acc, perf = meta["accuracy_metrics"], meta["performance"]

    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]

    # 1. title
    s = prs.slides.add_slide(blank)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()
    text(s, Inches(0.8), Inches(1.6), Inches(11.5), Inches(1.0), "Path Finder", size=54, color=WHITE, bold=True)
    text(s, Inches(0.8), Inches(2.6), Inches(11.5), Inches(1.0),
         "6-DoF trajectory from a degraded IMU alone, with rotor drag as a velocity sensor",
         size=24, color=RGBColor(0xC8, 0xD8, 0xF0))
    text(s, Inches(0.8), Inches(3.5), Inches(11.5), Inches(0.5),
         "Samsung PRISM XR Hackathon 2026  |  Track 3", size=18, color=RGBColor(0xC8, 0xD8, 0xF0))
    text(s, Inches(0.8), Inches(4.6), Inches(11.5), Inches(2.0),
         [(f"{TEAM}  |  {COLLEGE}", {"bold": True, "size": 20})] +
         [(f"{n}  -  {r}", {"size": 16}) for n, r in MEMBERS], color=WHITE)

    # 2. problem
    s = prs.slides.add_slide(blank)
    header(s, 2, "The problem", "Where did the device go? Only a damaged IMU file to answer it.")
    bullets(s, Inches(0.6), Inches(1.7), Inches(12), Inches(5), [
        ("Input:", "gyroscope and accelerometer only (timestamp, 3 x rate, 3 x acceleration). No camera, GPS, magnetometer or map."),
        ("Damage grows over time:", "noise ramp, drifting bias, scale errors, spikes, stuck readings, dropouts of up to 2 s, duplicated rows."),
        ("The last 5 seconds are all zeros:", "the position there has to be predicted."),
        ("Why it is hard:", "a 1 degree tilt error reads as 0.17 m/s^2 of false acceleration; integrated twice that is tens of metres within a minute."),
        ("Hard limits:", "single-thread Python, peak memory 8 MB, 20 ms of compute per second of data, exactly one TUM pose per input row with its timestamp."),
    ], size=18)

    # 3. solution
    s = prs.slides.add_slide(blank)
    header(s, 3, "Our solution", "Measure what can be measured, shrink what cannot, never let drift accumulate")
    bullets(s, Inches(0.6), Inches(1.7), Inches(12), Inches(5), [
        ("Rotor drag as a velocity sensor (key idea):", "on a drone the accelerometer axes across the thrust read -0.2 x velocity, so slow motion is measured, not integrated twice. Switched on automatically by motor vibration."),
        ("Clean before anything else:", "duplicates, stuck readings, spikes, nan rows and the dead tail removed; either column order detected from gravity."),
        ("Attitude:", "gyro integration with the bias from the still start (or fitted from the tilt drift), tilt pinned to gravity averaged over 30 s."),
        ("Position in the frequency domain:", "gains fitted per frequency band against motion-capture ground truth: fast motion kept, slow motion shrunk where tilt error dominates."),
        ("Blind 5 s:", "coast 0.3 s on the last velocity, then head for the take-off point (drones land where they took off)."),
        ("Lean:", "numpy only, array.array input buffers, 20 Hz position work, chunked output: 3 to 5 MB and 2 to 3.5 ms per second of data."),
    ], size=17)

    # 4. architecture
    s = prs.slides.add_slide(blank)
    header(s, 4, "System architecture", "One script, seven stages, one pass over the data")
    stages = [("Read", "csv / folder / zip\ninto C buffers"), ("Clean", "spikes, stuck,\nduplicates, nan"),
              ("Resample", "uniform grid,\ngaps > 0.3 s marked"), ("Attitude", "gyro + bias,\ngravity tilt fix"),
              ("Position", "FFT band gains\n+ rotor drag"), ("Blind 5 s", "coast, then\nhead home"),
              ("Write", "one TUM pose\nper input row")]
    bw, gap, y0 = 1.55, 0.22, 2.3
    for i, (name, desc) in enumerate(stages):
        x = Inches(0.6 + i * (bw + gap))
        box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(y0), Inches(bw), Inches(1.9))
        box.fill.solid()
        box.fill.fore_color.rgb = ORANGE if name == "Position" else (NAVY if i % 2 == 0 else BLUE)
        box.line.fill.background()
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = f"{i + 1}. {name}"; r.font.size = Pt(16); r.font.bold = True; r.font.color.rgb = WHITE
        for ln in desc.split("\n"):
            p = tf.add_paragraph(); p.alignment = PP_ALIGN.CENTER
            r = p.add_run(); r.text = ln; r.font.size = Pt(11); r.font.color.rgb = WHITE
        if i < len(stages) - 1:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + Inches(bw + 0.02), Inches(y0 + 0.8), Inches(gap - 0.04), Inches(0.3))
            a.fill.solid(); a.fill.fore_color.rgb = GREY; a.line.fill.background()
    bullets(s, Inches(0.6), Inches(4.6), Inches(12), Inches(2.3), [
        ("Drone or handheld?", "decided from the motor buzz inside 50 ms blocks (drone 1.1 to 1.9 m/s^2, handheld 0.2 to 0.4). Only drones use rotor drag."),
        ("Below 0.08 Hz", "horizontal position comes from integrating the drag velocity once; above it, from the accelerometer."),
        ("On the landing pad", "motor buzz drops: velocity is zero and height is held at the floor level."),
    ], size=16)

    # 5. results
    s = prs.slides.add_slide(blank)
    header(s, 5, "Results", "Error in metres after rigid alignment; stay-still = output the start point every time")
    rows = [["recording", "path: stay-still", "path: ours", "blind 5 s: stay-still", "blind 5 s: ours"],
            ["MH_04_difficult (drone)", "6.81", "4.07", "3.85", "0.85"],
            ["V1_02_medium (drone)", "1.78", "1.18", "1.04", "0.51"],
            ["V1_03_difficult (drone)", "1.58", "1.07", "1.27", "0.63"],
            ["tumvi_room1 (handheld, submitted)", "1.00", f"{acc['ate_rmse_meters']:.2f}", "0.63",
             f"{acc['blind_5s_rmse_meters']:.2f}"]]
    table(s, Inches(0.6), Inches(1.6), Inches(7.6), rows, [2.8, 1.15, 1.0, 1.4, 1.25], size=13, highlight_col=2)
    bullets(s, Inches(0.6), Inches(3.9), Inches(7.6), Inches(3), [
        ("49 runs, 3 groups (path / blind, x stay-still):", "tuning 0.62 / 0.58; held-out 0.68 / 0.90; five recordings never used for tuning 0.64 / 0.73."),
        ("Submitted file (tumvi_room1):", f"dropout windows {acc['dropout_gap_rmse_meters']:.2f} m (stay-still 0.87), "
                                          f"1 s drift {acc['rpe_1s_meters']:.2f} m, rotation {acc['rotation_rmse_degrees']:.1f} deg."),
        ("Resources:", f"peak memory {perf['peak_memory_mb']:.1f} MB of 8 (algorithm level, as the FAQ measures), {perf['runtime_ms_per_second']:.1f} ms per second of data of 20."),
    ], size=14)
    picture(s, "MH_04_difficult.png", Inches(8.4), Inches(1.6), w=Inches(4.6))
    picture(s, "tumvi_room1.png", Inches(8.4), Inches(3.6), w=Inches(4.6))
    text(s, Inches(8.4), Inches(5.6), Inches(4.6), Inches(0.6),
         "Top: MH_04 drone flight. Bottom: tumvi_room1 handheld. Grey: ground truth.", size=11, color=GREY)

    # 6. differentiators
    s = prs.slides.add_slide(blank)
    header(s, 6, "What sets it apart: rotor drag", "On a multirotor the accelerometer measures velocity")
    picture(s, "drag.png", Inches(0.5), Inches(1.5), w=Inches(7.6))
    bullets(s, Inches(8.3), Inches(1.5), Inches(4.7), Inches(5.4), [
        ("Physics:", "thrust is along one body axis, so the other two accelerometer axes see only rotor drag, a = -k v."),
        ("Measured:", "every EuRoC flight fits k = 0.18 to 0.22 per second, correlation up to 0.98 (left: V1_02)."),
        ("Why it matters:", "velocity integrated once drifts far less than acceleration integrated twice. MH_04 path 6.81 m to 4.07 m, blind 5 s 3.85 m to 0.85 m."),
        ("Details that made it work:", "drag read across the measured thrust axis (IMU mounted 20 deg off it), zero velocity on the pad, offsets solved from zero mean velocity."),
        ("Safe:", "switched on only by motor vibration; handheld data is untouched."),
    ], size=14)

    # 7. demo
    s = prs.slides.add_slide(blank)
    header(s, 7, "Demo and setup", "Python 3 and numpy, nothing else")
    code = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.7), Inches(12.1), Inches(2.9))
    code.fill.solid(); code.fill.fore_color.rgb = RGBColor(0x1E, 0x1E, 0x1E); code.line.fill.background()
    text(s, Inches(0.8), Inches(1.8), Inches(11.8), Inches(2.8), [
        ("# run", {"color": RGBColor(0x88, 0x88, 0x88)}),
        ("python src/main.py data/degraded/tumvi_room1/imu0/data.csv estimated_trajectory.txt", {}),
        ("# or in Docker", {"color": RGBColor(0x88, 0x88, 0x88), "before": 12}),
        ("docker build -t pathfinder .", {}),
        ("docker run --rm -v ${PWD}/data:/data pathfinder /data/<file>/imu0/data.csv /data/out.txt", {}),
        ("# score against the ground truth", {"color": RGBColor(0x88, 0x88, 0x88), "before": 12}),
        ("python tools/evalall.py", {}),
    ], size=15, color=RGBColor(0xE6, 0xE6, 0xE6), font="mono")
    bullets(s, Inches(0.6), Inches(4.9), Inches(12), Inches(2), [
        ("Input:", "an imu0/data.csv, a folder holding one, or a zip of it; either column order; header optional."),
        ("Output:", "estimated_trajectory.txt, one 'timestamp tx ty tz qx qy qz qw' line per input row, timestamps copied exactly."),
    ], size=16)

    # 8. robustness
    s = prs.slides.add_slide(blank)
    header(s, 8, "Robustness", "Tested on far worse than the official degradation")
    bullets(s, Inches(0.6), Inches(1.7), Inches(6.2), Inches(5.2), [
        ("Stress sets:", "2x noise and bias, jamming from the first second, 2 s dropouts, files starting mid-flight."),
        ("Odd inputs:", "50 to 400 Hz, a 6.5 min file, 5 s gaps, out-of-order and duplicated rows, nan values, CRLF and scientific notation, no header, swapped columns."),
        ("Edge cases:", "empty, one-row, 3 s, all-zero and blind-only files: no crashes, row count and timestamps always exact."),
        ("Held out honestly:", "settings tuned on 4 recordings, checked on 3 more, then on 5 fetched afterwards."),
    ], size=16)
    picture(s, "results_stress.png", Inches(6.9), Inches(1.6), w=Inches(6.0))
    text(s, Inches(6.9), Inches(4.5), Inches(6.0), Inches(1.6), [
        ("Peak memory 2.8 to 5.3 MB on every practice and stress run (limit 8),", {}),
        ("runtime 2.3 to 3.3 ms per second of data (limit 20).", {}),
        ("Path worse than stay-still: 1 run of 49 (a file cut to start mid-flight).", {"before": 8}),
    ], size=14, color=DARK)

    # 9. thanks
    s = prs.slides.add_slide(blank)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    bg.fill.solid(); bg.fill.fore_color.rgb = NAVY; bg.line.fill.background()
    text(s, Inches(0.8), Inches(1.8), Inches(11.5), Inches(1), "Thank you", size=50, color=WHITE, bold=True)
    text(s, Inches(0.8), Inches(3.0), Inches(11.5), Inches(3), [
        ("Questions welcome.", {"size": 22}),
        (REPO, {"size": 18, "before": 18}),
        (f"{TEAM}  |  {COLLEGE}", {"size": 18, "before": 18}),
        ("  |  ".join(n for n, _ in MEMBERS), {"size": 16}),
    ], color=RGBColor(0xC8, 0xD8, 0xF0))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    print(f"Generated presentation: {out}")


if __name__ == "__main__":
    create_deck()
