#!/usr/bin/env python3
"""
mark_stressed_vowels.py - mark the stressed vowel of each word in a TextGrid.

Input : TextGrids with a segments tier and a words tier.
Output: the same TextGrids, plus a COPY of the segments tier in which the
        vowel judged to be stressed gets a marker (default: *).  The original
        tiers are never changed, and the input files are never overwritten.

How the decision is made (version 1, duration only)
---------------------------------------------------
1. Every vowel duration is log-transformed and converted to a z-score,
   relative to the other tokens of the SAME vowel (e.g. all [a]) in the file
   (or in the whole folder, if you choose that). Vowel types with too few
   tokens fall back to the z-score over all vowels.
2. Inside each word, the vowel with the highest z-score is marked as stressed.
   Words with fewer vowels than "Min. vowels per word" are skipped.

This is a simple, transparent baseline: it assumes stressed vowels are
relatively longer than the unstressed vowels of the same word. Always check the
output (a CSV report with the z-scores and a margin is written next to the
TextGrids) before using it in an analysis.

Usage
-----
Run the script (Spyder's Run button works). A window opens, like a Praat form.
Prefer no window? Set USE_POPUP = False and fill in SETTINGS below.

Requires: praat-parselmouth  (tkinter comes with Python)
"""
import csv
import json
import math
import statistics
import unicodedata
from bisect import bisect_left
from collections import defaultdict, namedtuple
from pathlib import Path

import parselmouth
from parselmouth.praat import call

# ============================================================================
# SETTINGS - used when USE_POPUP = False (and as starting values for the popup)
# ============================================================================
USE_POPUP = True

SETTINGS = {
    "input_folder": r"C:\path\to\folder\with\TextGrids",
    "output_folder": "",          # empty = "stress_marked" inside the input folder
    "segments_tier": "phones",  # tier name or number
    "words_tier": "words",        # tier name or number
    "alphabet": "SAMPA",          # "SAMPA" or "IPA"
    "vowels": "",                 # empty = default list for the alphabet (see below)
    "marker": "*",
    "marker_position": "after",   # "after" -> a*    "before" -> *a
    "new_tier_name": "",          # empty = "<segments tier name>-stress"
    "normalize_over": "file",     # "file" or "folder" (all files = one speaker)
    "min_vowels_in_word": 2,      # words with fewer vowels are not marked
    "min_tokens_per_vowel": 3,    # fewer tokens of a vowel -> use all-vowel z-score
    "write_report": True,         # CSV with z-scores for every vowel
}

# Edit these if your labels differ. Separate labels with spaces.
DEFAULT_VOWELS = {
    "SAMPA": "a A e E i I o O u U @ 6 a~ e~ i~ o~ u~ 6~",
    "IPA": "a e ɛ i ɪ o ɔ u ʊ ə ɐ ɑ ɨ ã ẽ ĩ õ ũ ɐ̃",
}

SETTINGS_FILE = Path.home() / ".stress_vowel_marker.json"

Interval = namedtuple("Interval", "index label start end")
Word = namedtuple("Word", "interval vowels")


# ============================================================================
# TextGrid helpers (through Praat itself, so encodings just work)
# ============================================================================
def nfc(text):
    """Unicode-normalise so that 'ã' typed either way matches."""
    return unicodedata.normalize("NFC", text.strip())


def find_tier(tg, tier):
    """1-based tier number from a name or a number."""
    n_tiers = call(tg, "Get number of tiers")
    if str(tier).strip().isdigit():
        number = int(tier)
        if not 1 <= number <= n_tiers:
            raise ValueError(f"tier {number} out of range (1-{n_tiers})")
        return number
    for i in range(1, n_tiers + 1):
        if call(tg, "Get tier name", i) == str(tier).strip():
            return i
    raise ValueError(f"tier '{tier}' not found")


def read_tier(tg, tier_number):
    n = call(tg, "Get number of intervals", tier_number)
    return [
        Interval(
            i,
            call(tg, "Get label of interval", tier_number, i),
            call(tg, "Get start time of interval", tier_number, i),
            call(tg, "Get end time of interval", tier_number, i),
        )
        for i in range(1, n + 1)
    ]


# ============================================================================
# Core logic (plain Python, no Praat needed)
# ============================================================================
def group_vowels_by_word(segments, words, vowel_set):
    """For every labelled word, list the vowel segments whose midpoint lies inside it."""
    vowels = [s for s in segments if nfc(s.label) in vowel_set]
    mids = [(s.start + s.end) / 2 for s in vowels]  # sorted, like the segments
    out = []
    for w in words:
        if not w.label.strip():
            continue
        lo, hi = bisect_left(mids, w.start), bisect_left(mids, w.end)
        out.append(Word(w, vowels[lo:hi]))
    return out


def log_dur(interval):
    return math.log(max(interval.end - interval.start, 1e-4))


Stat = namedtuple("Stat", "mean sd n")


def build_stats(grouped):
    """grouped: {scope: [Word, ...]} -> {(scope, vowel label or None): Stat}"""
    logs = defaultdict(list)
    for scope, words in grouped.items():
        for word in words:
            for v in word.vowels:
                d = log_dur(v)
                logs[(scope, nfc(v.label))].append(d)
                logs[(scope, None)].append(d)
    return {
        key: Stat(statistics.mean(vals), statistics.stdev(vals) if len(vals) > 1 else 0.0, len(vals))
        for key, vals in logs.items()
    }


def zscore(interval, scope, stats, min_tokens):
    """z-score of a vowel's log duration, and which reference was used."""
    d = log_dur(interval)
    own = stats.get((scope, nfc(interval.label)))
    if own and own.n >= min_tokens and own.sd > 0:
        return (d - own.mean) / own.sd, "vowel"
    pooled = stats.get((scope, None))
    if pooled and pooled.sd > 0:
        return (d - pooled.mean) / pooled.sd, "pooled"
    return 0.0, "none"


def decide_word(word, scope, stats, min_vowels, min_tokens):
    """
    Return one dict per vowel of the word with its z-score, plus which one is stressed.
    'stressed' is None for words that are skipped (too few vowels).
    """
    zs = [zscore(v, scope, stats, min_tokens) for v in word.vowels]
    rows = [{"vowel": v, "z": z, "basis": basis, "stressed": None, "margin": None}
            for v, (z, basis) in zip(word.vowels, zs)]
    if len(word.vowels) >= max(min_vowels, 1):
        best = max(range(len(rows)), key=lambda i: rows[i]["z"])
        ordered = sorted((r["z"] for r in rows), reverse=True)
        margin = ordered[0] - ordered[1] if len(ordered) > 1 else None
        for i, r in enumerate(rows):
            r["stressed"] = 1 if i == best else 0
            r["margin"] = margin
    return rows


def mark_label(label, marker, position):
    return marker + label if position == "before" else label + marker


# ============================================================================
# Batch processing
# ============================================================================
def run(cfg, log=print):
    in_dir = Path(cfg["input_folder"])
    out_dir = Path(cfg["output_folder"]) if str(cfg["output_folder"]).strip() else in_dir / "stress_marked"
    if out_dir.resolve() == in_dir.resolve():
        raise ValueError("The output folder must be different from the input folder "
                         "(the original TextGrids are never overwritten).")
    out_dir.mkdir(parents=True, exist_ok=True)

    vowel_text = str(cfg["vowels"]).strip() or DEFAULT_VOWELS[cfg["alphabet"]]
    vowel_set = {nfc(v) for v in vowel_text.replace(",", " ").split()}
    marker, position = cfg["marker"], cfg["marker_position"]
    min_vowels = int(cfg["min_vowels_in_word"])
    min_tokens = int(cfg["min_tokens_per_vowel"])

    files = sorted(p for p in in_dir.glob("*") if p.suffix.lower() == ".textgrid")
    if not files:
        raise FileNotFoundError(f"No TextGrid files found in {in_dir}")

    # ---- pass 1: read everything and collect vowel durations -----------------
    loaded, grouped = [], {}
    for path in files:
        try:
            tg = parselmouth.read(str(path))
            seg_no = find_tier(tg, cfg["segments_tier"])
            word_no = find_tier(tg, cfg["words_tier"])
            words = group_vowels_by_word(read_tier(tg, seg_no), read_tier(tg, word_no), vowel_set)
        except Exception as err:
            log(f"  skipping {path.name}: {err}")
            continue
        scope = path.name if cfg["normalize_over"] == "file" else "ALL"
        grouped.setdefault(scope, []).extend(words)
        loaded.append((path, tg, seg_no, scope, words))

    stats = build_stats(grouped)

    # ---- pass 2: decide, edit the TextGrid, save -----------------------------
    report, summary = [], defaultdict(int)
    for path, tg, seg_no, scope, words in loaded:
        seg_name = call(tg, "Get tier name", seg_no)
        new_name = str(cfg["new_tier_name"]).strip() or f"{seg_name}-stress"
        existing = [call(tg, "Get tier name", i) for i in range(1, call(tg, "Get number of tiers") + 1)]
        if new_name in existing:
            log(f"  skipping {path.name}: a tier called '{new_name}' already exists")
            continue

        new_tier = seg_no + 1
        call(tg, "Duplicate tier", seg_no, new_tier, new_name)

        for word in words:
            rows = decide_word(word, scope, stats, min_vowels, min_tokens)
            n = len(rows)
            if rows and rows[0]["stressed"] is None:
                summary["words_skipped"] += 1
            elif rows:
                summary["words_marked"] += 1
            for k, r in enumerate(rows):
                v = r["vowel"]
                if r["stressed"] == 1:
                    call(tg, "Set interval text", new_tier, v.index,
                         mark_label(v.label, marker, position))
                    summary["vowels_marked"] += 1
                report.append({
                    "file": path.name,
                    "word": word.interval.label,
                    "word_start": round(word.interval.start, 4),
                    "word_end": round(word.interval.end, 4),
                    "n_vowels": n,
                    "vowel_from_start": k + 1,
                    "vowel_from_end": n - k,
                    "segment_label": v.label,
                    "seg_start": round(v.start, 4),
                    "seg_end": round(v.end, 4),
                    "dur_ms": round((v.end - v.start) * 1000, 1),
                    "z": round(r["z"], 3),
                    "norm_basis": r["basis"],
                    "stressed": "" if r["stressed"] is None else r["stressed"],
                    "margin": "" if r["margin"] is None else round(r["margin"], 3),
                })

        call(tg, "Save as text file", str(out_dir / path.name))
        summary["files"] += 1
        log(f"  {path.name}: done")

    if cfg.get("write_report") and report:
        report_path = out_dir / "stress_report.csv"
        with open(report_path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(report[0]))
            writer.writeheader()
            writer.writerows(report)
        summary["report"] = str(report_path)

    summary["output_folder"] = str(out_dir)
    return dict(summary)


def format_summary(s):
    return (f"Files processed: {s.get('files', 0)}\n"
            f"Words with a marked vowel: {s.get('words_marked', 0)}\n"
            f"Words skipped (too few vowels): {s.get('words_skipped', 0)}\n"
            f"Vowels marked: {s.get('vowels_marked', 0)}\n\n"
            f"Saved in: {s.get('output_folder', '')}")


# ============================================================================
# Popup window (tkinter, ships with Python)
# ============================================================================
def load_saved():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(cfg):
    try:
        SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def ask_settings(initial):
    """Show a Praat-style form. Returns a settings dict, or None if cancelled."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    try:  # sharper text on Windows
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.title("Mark stressed vowels")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=14)
    frm.grid()

    text_keys = ["input_folder", "output_folder", "segments_tier", "words_tier", "alphabet", "vowels",
                 "marker", "marker_position", "new_tier_name", "normalize_over",
                 "min_vowels_in_word", "min_tokens_per_vowel"]
    var = {k: tk.StringVar(value=str(initial.get(k, ""))) for k in text_keys}
    report_var = tk.BooleanVar(value=bool(initial.get("write_report", True)))
    if not var["vowels"].get().strip():
        var["vowels"].set(DEFAULT_VOWELS.get(var["alphabet"].get(), DEFAULT_VOWELS["SAMPA"]))

    state = {"row": 0, "result": None}

    def next_row():
        state["row"] += 1
        return state["row"] - 1

    def folder_row(label, key):
        r = next_row()
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=var[key], width=54).grid(row=r, column=1, pady=3)

        def browse():
            chosen = filedialog.askdirectory(initialdir=var[key].get() or str(Path.home()))
            if chosen:
                var[key].set(chosen)

        ttk.Button(frm, text="Browse...", command=browse).grid(row=r, column=2, padx=(6, 0))

    def entry_row(label, key, width=54):
        r = next_row()
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=var[key], width=width).grid(row=r, column=1, sticky="w", pady=3)

    def radio_row(label, key, options, command=None):
        r = next_row()
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3)
        box = ttk.Frame(frm)
        box.grid(row=r, column=1, sticky="w")
        for text, value in options:
            ttk.Radiobutton(box, text=text, value=value, variable=var[key],
                            command=command).pack(side="left", padx=(0, 14))

    def on_alphabet():
        var["vowels"].set(DEFAULT_VOWELS[var["alphabet"].get()])

    folder_row("Input folder (TextGrids):", "input_folder")
    folder_row("Output folder:", "output_folder")
    ttk.Label(frm, text="(empty output folder = 'stress_marked' inside the input folder)",
              foreground="gray").grid(row=next_row(), column=1, sticky="w")
    entry_row("Segments tier (name or number):", "segments_tier", 24)
    entry_row("Words tier (name or number):", "words_tier", 24)
    radio_row("Segment alphabet:", "alphabet", [("SAMPA", "SAMPA"), ("IPA", "IPA")], on_alphabet)
    entry_row("Vowels to analyse:", "vowels")
    entry_row("Stress marker:", "marker", 6)
    radio_row("Marker position:", "marker_position", [("after the label (a*)", "after"),
                                                      ("before the label (*a)", "before")])
    entry_row("New tier name:", "new_tier_name", 24)
    ttk.Label(frm, text="(empty = '<segments tier>-stress')", foreground="gray").grid(
        row=next_row(), column=1, sticky="w")
    radio_row("Compare durations within:", "normalize_over",
              [("each file", "file"), ("all files together", "folder")])
    entry_row("Min. vowels per word:", "min_vowels_in_word", 6)
    entry_row("Min. tokens per vowel type:", "min_tokens_per_vowel", 6)
    ttk.Checkbutton(frm, text="Save a CSV report with z-scores", variable=report_var).grid(
        row=next_row(), column=1, sticky="w", pady=3)

    def on_run(event=None):
        cfg = {k: var[k].get().strip() for k in text_keys}
        cfg["write_report"] = report_var.get()
        problems = []
        if not Path(cfg["input_folder"]).is_dir():
            problems.append("The input folder does not exist.")
        if not cfg["segments_tier"] or not cfg["words_tier"]:
            problems.append("Fill in both tier names.")
        if not cfg["marker"]:
            problems.append("The stress marker cannot be empty.")
        for key, label in (("min_vowels_in_word", "Min. vowels per word"),
                           ("min_tokens_per_vowel", "Min. tokens per vowel type")):
            if not cfg[key].isdigit():
                problems.append(f"'{label}' must be a whole number.")
        if problems:
            messagebox.showerror("Check your settings", "\n".join(problems), parent=root)
            return
        state["result"] = cfg
        root.destroy()

    buttons = ttk.Frame(frm)
    buttons.grid(row=next_row(), column=0, columnspan=3, sticky="e", pady=(12, 0))
    ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
    ttk.Button(buttons, text="Run", command=on_run).pack(side="right")
    root.bind("<Return>", on_run)

    root.update_idletasks()
    root.lift()  # make sure the window is not hidden behind Spyder
    root.attributes("-topmost", True)
    root.after(400, lambda: root.attributes("-topmost", False))
    root.mainloop()
    return state["result"]


def show_message(title, text, error=False):
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    (messagebox.showerror if error else messagebox.showinfo)(title, text, parent=root)
    root.destroy()


# ============================================================================
def main():
    cfg = dict(SETTINGS)
    if USE_POPUP:
        cfg.update(load_saved())
        chosen = ask_settings(cfg)
        if not chosen:
            print("Cancelled.")
            return
        cfg = chosen
        save_settings(cfg)

    print("Processing...")
    try:
        summary = run(cfg)
    except Exception as err:
        print(f"Error: {err}")
        if USE_POPUP:
            show_message("Error", str(err), error=True)
        return
    print(format_summary(summary))
    if USE_POPUP:
        show_message("Done", format_summary(summary))


if __name__ == "__main__":
    main()
