import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OURS = "#2a78d6"
BASE = "#8f8d87"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"

SEQS = ["V1_02_medium", "V1_03_difficult", "MH_04_difficult", "tumvi_room1"]
SEQ_NAMES = {
    "V1_02_medium": "V1_02 medium\n(drone)",
    "V1_03_difficult": "V1_03 difficult\n(drone)",
    "MH_04_difficult": "MH_04 difficult\n(drone, large hall)",
    "tumvi_room1": "TUM-VI room1\n(handheld)",
}
STRESS = [
    ("degraded", "Organisers' damage"),
    ("degraded_raw", "Same, raw column order"),
    ("early", "Damage from the start"),
    ("harsh", "Twice the damage"),
    ("harsh_raw", "Twice, raw column order"),
    ("gaps2s", "Gaps of 2 to 3.5 s"),
]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "text.color": INK,
    "axes.labelcolor": INK2,
    "axes.edgecolor": GRID,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def load(path, label, base):
    rows = defaultdict(dict)
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["label"] in (label, base):
                rows[r["label"]][(r["set"], r["seq"])] = r
    return rows[label], rows[base]


def num(row, key):
    try:
        return float(row[key])
    except (KeyError, ValueError):
        return float("nan")


def tidy(ax, xlabel):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", color=GRID)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel(xlabel)


def chart_errors(ours, base, out):
    metrics = [("ate_m", "Whole path"), ("blind_m", "Blind last 5 s"), ("gap_m", "Around dropouts")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    top = max(num(base[("degraded", s)], m) for s in SEQS for m, _ in metrics)
    for ax, (m, title) in zip(axes, metrics):
        for y, s in enumerate(SEQS):
            b, o = num(base[("degraded", s)], m), num(ours[("degraded", s)], m)
            ax.plot([o, b], [y, y], color=GRID, linewidth=3, solid_capstyle="round", zorder=1)
            ax.scatter([b], [y], s=70, color=BASE, zorder=2, edgecolor=SURFACE, linewidth=2)
            ax.scatter([o], [y], s=70, color=OURS, zorder=3, edgecolor=SURFACE, linewidth=2)
            ax.annotate(f"{o:.2f}", (o, y), xytext=(-9, 0), textcoords="offset points",
                        ha="right", va="center", fontsize=9.5, color=INK)
            ax.annotate(f"{b:.2f}", (b, y), xytext=(9, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=9.5, color=INK2)
        ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)
        ax.set_xlim(-0.9, top * 1.15)
        ax.set_ylim(len(SEQS) - 0.4, -0.7)
        tidy(ax, "error (m)")
    axes[0].set_yticks(range(len(SEQS)), [SEQ_NAMES[s] for s in SEQS])
    fig.legend(handles=[
        plt.Line2D([], [], marker="o", linestyle="", color=OURS, markersize=8, label="our estimate"),
        plt.Line2D([], [], marker="o", linestyle="", color=BASE, markersize=8, label="stay-still baseline"),
    ], loc="upper right", ncol=2, frameon=False, bbox_to_anchor=(0.99, 1.0))
    fig.suptitle("Error after alignment, organisers' damage (lower is better)",
                 x=0.01, ha="left", fontsize=13.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out, dpi=200)
    plt.close(fig)


def chart_stress(ours, base, out):
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ys = range(len(STRESS))
    for y, (key, _) in zip(ys, STRESS):
        r = [num(ours[(key, s)], "ate_m") / num(base[(key, s)], "ate_m") for s in SEQS]
        mean = sum(r) / len(r)
        ax.plot([min(r), max(r)], [y, y], color=OURS, linewidth=2, alpha=0.45,
                solid_capstyle="round", zorder=1)
        ax.scatter([mean], [y], s=70, color=OURS, zorder=3, edgecolor=SURFACE, linewidth=2)
        ax.annotate(f"{mean:.2f}", (mean, y), xytext=(0, 9), textcoords="offset points",
                    ha="center", fontsize=9.5, color=INK)
    ax.axvline(1.0, color=BASE, linewidth=2, zorder=2)
    ax.annotate("stay-still = 1.0", (1.0, len(STRESS) - 0.5), xytext=(-6, 0),
                textcoords="offset points", ha="right", va="center", fontsize=9.5, color=INK2)
    ax.set_yticks(list(ys), [name for _, name in STRESS])
    ax.set_xlim(0, 1.1)
    ax.set_ylim(len(STRESS) - 0.3, -0.7)
    tidy(ax, "whole-path error as a fraction of stay-still")
    ax.set_title("Whole-path error below stay-still for every damage type and recording",
                 loc="left", fontsize=12.5, color=INK, pad=22)
    ax.text(0, 1.02, "dot: mean of the 4 recordings, bar: best to worst recording",
            transform=ax.transAxes, fontsize=9.5, color=INK2)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def chart_budget(ours, out):
    full = [k for k in ours if k[0] in dict(STRESS)]
    panels = [
        ("ms_per_s", 20.0, "Runtime (ms per second of data)", "ms/s"),
        ("mem_mb", 8.0, "Peak memory (MB, tracemalloc)", "MB"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11, 2.6))
    for ax, (key, limit, title, unit) in zip(axes, panels):
        vals = [num(ours[k], key) for k in full]
        lo, hi = min(vals), max(vals)
        ax.barh([0], [hi], height=0.42, color=OURS, zorder=2)
        ax.axvline(limit, color=INK, linewidth=2, zorder=4)
        ax.annotate(f"limit {limit:g}", (limit, 0.36), xytext=(-5, 0), textcoords="offset points",
                    ha="right", va="center", fontsize=9.5, color=INK)
        ax.annotate(f"worst run {hi:.1f} {unit}  (best {lo:.1f})", (0, 0.24), xytext=(0, 4),
                    textcoords="offset points", va="bottom", fontsize=10.5, color=INK)
        ax.set_xlim(0, limit * 1.05)
        ax.set_ylim(-0.6, 0.6)
        ax.set_yticks([])
        tidy(ax, "")
        ax.set_title(title, loc="left", fontsize=12, color=INK, pad=8)
    fig.text(0.01, 0.02, f"{len(full)} runs: 4 recordings x 6 damage types, on a laptop. "
             "Memory excludes the NumPy import, as the FAQ measures at algorithm level.",
             fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(out, dpi=200)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="sarthak-v7")
    ap.add_argument("--base", default="stay-still")
    ap.add_argument("--results", default="results/results.csv")
    ap.add_argument("--out", default="docs/figures")
    args = ap.parse_args()

    ours, base = load(args.results, args.label, args.base)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    chart_errors(ours, base, out / "results_errors.png")
    chart_stress(ours, base, out / "results_stress.png")
    chart_budget(ours, out / "results_budget.png")
    print("wrote", ", ".join(str(out / n) for n in
                             ("results_errors.png", "results_stress.png", "results_budget.png")))


if __name__ == "__main__":
    main()
