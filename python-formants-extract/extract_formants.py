#!/usr/bin/env python3
"""
extract_formants.py - batch formant extraction from wav + TextGrid pairs.

A Python replacement for the typical Praat "formants at the vowel midpoint"
script. Requires only praat-parselmouth (pip install praat-parselmouth).

For every labelled interval on a chosen tier (e.g. vowels) it measures
F1-F3 (and bandwidths B1-B3) at one or more relative time points and writes
one row per token to a CSV file.

Examples
--------
  # midpoint of every non-empty interval on tier "phones"
  python extract_formants.py data/ -o formants.csv --tier phones

  # only some vowels, at 25/50/75% of the interval, with a word tier for context
  python extract_formants.py data/ -o formants.csv --tier phones \
      --vowels a,e,i,o,u,ɛ,ɔ --points 0.25 0.5 0.75 --word-tier words

  # pick the formant ceiling automatically for each file (speaker)
  python extract_formants.py data/ -o formants.csv --tier phones \
      --vowels a,e,i,o,u --auto-ceiling
"""
import argparse
import csv
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import parselmouth
from parselmouth.praat import call

NAN = float("nan")

# ----------------------------------------------------------------------------
# Running from Spyder (Run button) or by double-click?
# Edit this list and press Run. It is only used when the script is started
# WITHOUT command-line arguments; otherwise the real arguments win.
# ----------------------------------------------------------------------------
DEFAULT_ARGS = [
    r"C:\Users\VitorPrado\Desktop\Mestrado\2025\Áudios cortados + textgrids\textgrids processados",
    "--tier", "phones",
    "--vowels", "a,e,i,o,u",
    "--auto-ceiling",
    "-o", "formants.csv",
]


# ----------------------------------------------------------------------------
# TextGrid helpers (all done through Praat itself, so encodings just work)
# ----------------------------------------------------------------------------
def find_tier(tg, tier):
    """Return the 1-based tier number from a name or a number."""
    n_tiers = call(tg, "Get number of tiers")
    if str(tier).isdigit():
        number = int(tier)
        if not 1 <= number <= n_tiers:
            raise ValueError(f"tier {number} out of range (1-{n_tiers})")
        return number
    for i in range(1, n_tiers + 1):
        if call(tg, "Get tier name", i) == tier:
            return i
    raise ValueError(f"tier '{tier}' not found")


def intervals(tg, tier_number):
    """Yield (index, label, start, end) for every interval of a tier."""
    n = call(tg, "Get number of intervals", tier_number)
    for i in range(1, n + 1):
        yield (
            i,
            call(tg, "Get label of interval", tier_number, i),
            call(tg, "Get start time of interval", tier_number, i),
            call(tg, "Get end time of interval", tier_number, i),
        )


def label_at(tg, tier_number, time):
    """Label of the interval covering `time` on a tier."""
    i = call(tg, "Get interval at time", tier_number, time)
    return call(tg, "Get label of interval", tier_number, i) if i else ""


# ----------------------------------------------------------------------------
# Formant measurement
# ----------------------------------------------------------------------------
def get_formants(snd, ceiling, n_formants, window, time_step):
    return snd.to_formant_burg(
        time_step=time_step,
        max_number_of_formants=n_formants,
        maximum_formant=ceiling,
        window_length=window,
        pre_emphasis_from=50.0,
    )


def value(formant, number, time, bandwidth=False):
    f = formant.get_bandwidth_at_time if bandwidth else formant.get_value_at_time
    v = f(number, time)
    return NAN if v is None or math.isnan(v) else v


def pick_ceiling(snd, tokens, ceilings, n_formants, window, time_step):
    """
    Choose the formant ceiling for one speaker/file.

    Simple version of the 'minimise vowel variance' idea: for each candidate
    ceiling, measure F1 and F2 at the midpoint of every token, then take the
    average within-vowel standard deviation (in log Hz, so F1 and F2 weigh
    the same). The ceiling with the least scatter wins.
    """
    best, best_score = None, float("inf")
    for ceiling in ceilings:
        formant = get_formants(snd, ceiling, n_formants, window, time_step)
        by_vowel = defaultdict(lambda: ([], []))
        for label, start, end in tokens:
            mid = (start + end) / 2
            f1, f2 = value(formant, 1, mid), value(formant, 2, mid)
            if not (math.isnan(f1) or math.isnan(f2)):
                by_vowel[label][0].append(math.log(f1))
                by_vowel[label][1].append(math.log(f2))
        sds = [
            statistics.stdev(vals)
            for f1s, f2s in by_vowel.values()
            if len(f1s) >= 2
            for vals in (f1s, f2s)
        ]
        if sds:
            score = statistics.mean(sds)
            if score < best_score:
                best, best_score = ceiling, score
    return best


# ----------------------------------------------------------------------------
# Main per-file routine
# ----------------------------------------------------------------------------
def process_pair(wav, textgrid, args, label_ok):
    snd = parselmouth.Sound(str(wav))
    tg = parselmouth.read(str(textgrid))
    tier = find_tier(tg, args.tier)
    word_tier = find_tier(tg, args.word_tier) if args.word_tier else None

    all_ivs = list(intervals(tg, tier))
    tokens = [
        (label, start, end)
        for _, label, start, end in all_ivs
        if label.strip() and label_ok(label) and end - start >= args.min_dur
    ]
    if not tokens:
        return []

    ceiling = args.ceiling
    if args.auto_ceiling:
        candidates = list(range(args.ceiling_min, args.ceiling_max + 1, args.ceiling_step))
        chosen = pick_ceiling(snd, tokens, candidates, args.n_formants, args.window, args.time_step)
        ceiling = chosen or args.ceiling

    formant = get_formants(snd, ceiling, args.n_formants, args.window, args.time_step)

    rows = []
    for idx, label, start, end in all_ivs:
        if not (label.strip() and label_ok(label)) or end - start < args.min_dur:
            continue
        row = {
            "file": wav.stem,
            "interval": idx,
            "label": label,
            "prev": all_ivs[idx - 2][1] if idx > 1 else "",
            "next": all_ivs[idx][1] if idx < len(all_ivs) else "",
            "start": round(start, 4),
            "end": round(end, 4),
            "dur_ms": round((end - start) * 1000, 1),
            "ceiling": ceiling,
        }
        if word_tier:
            row["word"] = label_at(tg, word_tier, (start + end) / 2)
        for p in args.points:
            t = start + p * (end - start)
            pct = f"{round(p * 100):d}"
            for n in (1, 2, 3):
                row[f"F{n}_{pct}"] = round(value(formant, n, t), 1)
                row[f"B{n}_{pct}"] = round(value(formant, n, t, bandwidth=True), 1)
        rows.append(row)
    return rows


def find_pairs(folder):
    """Match each .wav with a .TextGrid of the same name in the same folder."""
    for wav in sorted(Path(folder).rglob("*.wav")):
        tg = wav.with_suffix(".TextGrid")
        if tg.exists():
            yield wav, tg
        else:
            print(f"  skipping {wav.name}: no matching TextGrid", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="folder with .wav and same-named .TextGrid files (searched recursively)")
    ap.add_argument("-o", "--output", default="formants.csv")
    ap.add_argument("--tier", required=True, help="tier name or number holding the vowel intervals")
    ap.add_argument("--word-tier", help="optional tier whose label is added as a 'word' column")
    sel = ap.add_mutually_exclusive_group()
    sel.add_argument("--vowels", help="comma-separated labels to keep, e.g. a,e,i,o,u")
    sel.add_argument("--regex", help="regular expression a label must match (re.fullmatch)")
    ap.add_argument("--points", type=float, nargs="+", default=[0.5],
                    help="relative positions inside the interval (default: 0.5)")
    ap.add_argument("--min-dur", type=float, default=0.03, help="skip intervals shorter than this (s)")
    ap.add_argument("--ceiling", type=int, default=5500, help="max formant in Hz (5000 male, 5500 female)")
    ap.add_argument("--auto-ceiling", action="store_true", help="choose the ceiling per file")
    ap.add_argument("--ceiling-min", type=int, default=4500)
    ap.add_argument("--ceiling-max", type=int, default=6500)
    ap.add_argument("--ceiling-step", type=int, default=250)
    ap.add_argument("--n-formants", type=int, default=5)
    ap.add_argument("--window", type=float, default=0.025, help="analysis window length (s)")
    ap.add_argument("--time-step", type=float, default=0.005)
    args = ap.parse_args(None if len(sys.argv) > 1 else DEFAULT_ARGS)

    if not Path(args.folder).is_dir():
        sys.exit(f"Folder not found: {args.folder}\nEdit DEFAULT_ARGS at the top of the script "
                 "or pass the folder on the command line.")

    if args.vowels:
        keep = {v.strip() for v in args.vowels.split(",") if v.strip()}
        label_ok = lambda lab: lab in keep
    elif args.regex:
        pattern = re.compile(args.regex)
        label_ok = lambda lab: pattern.fullmatch(lab) is not None
    else:
        label_ok = lambda lab: True

    all_rows = []
    for wav, tg in find_pairs(args.folder):
        print(f"processing {wav.name}")
        all_rows.extend(process_pair(wav, tg, args, label_ok))

    if not all_rows:
        sys.exit("No tokens found. Check --tier and --vowels/--regex.")

    # union of columns, in first-seen order
    columns = list(dict.fromkeys(k for r in all_rows for k in r))
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"{len(all_rows)} tokens written to {args.output}")


if __name__ == "__main__":
    main()