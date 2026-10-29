#!/usr/bin/env python3
"""
plot_vowel_space.py - F1/F2 vowel plot (with ellipses) from extract_formants.py output.

  python plot_vowel_space.py formants.csv -o vowels.png
  python plot_vowel_space.py formants.csv --point 50 --facet-by file -o vowels.pdf
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Ellipse
import sys

# Running from Spyder (Run button)? Edit this list and press Run.
# Only used when the script is started WITHOUT command-line arguments.
DEFAULT_ARGS = ["formants.csv", "-o", "vowel_space.png"]


def get_cli_args():
    """Real command-line args, or DEFAULT_ARGS when run from Spyder's Run button.
    Spyder's %runfile can leak its own --wdir flag into sys.argv; drop it."""
    argv, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
            if not a.startswith("-"):
                continue
        if a.startswith("--wdir"):
            skip = "=" not in a
            continue
        argv.append(a)
    return argv or DEFAULT_ARGS


def draw_ellipse(ax, x, y, color, n_std=1.0):
    """Covariance ellipse (n_std standard deviations) around the cloud."""
    if len(x) < 3:
        return
    cov = np.cov(x, y)
    vals, vecs = np.linalg.eigh(cov)
    order = vals.argsort()[::-1]
    vals, vecs = vals[order], vecs[:, order]
    angle = np.degrees(np.arctan2(vecs[1, 0], vecs[0, 0]))
    width, height = 2 * n_std * np.sqrt(vals)
    ax.add_patch(Ellipse((np.mean(x), np.mean(y)), width, height, angle=angle,
                         fill=False, edgecolor=color, linewidth=1.5))


def plot(ax, data, f1, f2, title=None):
    colors = plt.cm.tab10.colors
    for i, (label, g) in enumerate(data.groupby("label")):
        c = colors[i % len(colors)]
        ax.scatter(g[f2], g[f1], s=10, alpha=0.35, color=c)
        draw_ellipse(ax, g[f2].to_numpy(), g[f1].to_numpy(), c)
        ax.text(g[f2].mean(), g[f1].mean(), label, fontsize=14,
                weight="bold", ha="center", va="center", color=c)
    # phonetic convention: origin at top right
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.set_xlabel("F2 (Hz)")
    ax.set_ylabel("F1 (Hz)")
    if title:
        ax.set_title(title)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("-o", "--output", default="vowel_space.png")
    ap.add_argument("--point", default="50", help="which time point to plot, e.g. 50 for F1_50/F2_50")
    ap.add_argument("--facet-by", help="column to make one panel per value (e.g. file)")
    ap.add_argument("--min-count", type=int, default=3, help="drop vowels with fewer tokens")
    args = ap.parse_args(get_cli_args())

    f1, f2 = f"F1_{args.point}", f"F2_{args.point}"
    df = pd.read_csv(args.csv).dropna(subset=[f1, f2])
    counts = df["label"].value_counts()
    df = df[df["label"].isin(counts[counts >= args.min_count].index)]

    if args.facet_by:
        groups = list(df.groupby(args.facet_by))
        cols = min(3, len(groups))
        rows = -(-len(groups) // cols)
        fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4.5 * rows), squeeze=False)
        for ax, (name, g) in zip(axes.flat, groups):
            plot(ax, g, f1, f2, title=str(name))
        for ax in list(axes.flat)[len(groups):]:
            ax.axis("off")
    else:
        fig, ax = plt.subplots(figsize=(6, 5))
        plot(ax, df, f1, f2)

    fig.tight_layout()
    fig.savefig(args.output, dpi=200)
    print(f"saved {args.output}")


if __name__ == "__main__":
    main()