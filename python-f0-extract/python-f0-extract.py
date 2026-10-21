#!/usr/bin/env python3
r"""
extract_pitch_full.py -- extract F0 measures from Praat TextGrids + WAV files.

Python port (via parselmouth, i.e. Praat's own engine) of a Praat script used
to analyse F0 in word-level, syllable-level and vowel-level spans.

For every  <name>.wav  with a matching  <name>.TextGrid  in the input folder,
it does a single pass and writes two tab-separated files:

  1) pitch_summary.txt        one row per syllable (word-level measures are
                              repeated on every syllable row of that word):
                              F0 extrema, peak/valley times, rise/fall velocity
                              and excursion (Hz and semitones), voicing
                              proportion, vowel boundaries, peak alignment.
  2) pitch_contour_points.txt long format: F0 sampled at time-normalised points
                              for word, syllable AND vowel spans (the column
                              "level" says which).

Required TextGrid structure (interval tiers; names are configurable):
  - "mainwords": the words to analyse (empty intervals are ignored)
  - "syll"     : syllables
  - "phones"   : segments (the first interval whose label is in --vowels is
                 taken as the vowel of each syllable)

Pitch is tracked in two passes: a wide pass (60-400 Hz by default) to estimate
each file's median F0, then a final pass with a range derived from that median
(floor = 0.75 x median, ceiling = 2.5 x median by default).
Check that these settings are appropriate for your speakers and recordings.

Install:  pip install praat-parselmouth

Usage:    python extract_pitch_full.py --input_folder path/to/data
          python extract_pitch_full.py --input_folder data --output_folder out \
                 --vowels "a e i o u" --points_per_word 30
          python extract_pitch_full.py --help

From Python / Spyder / Jupyter:
          from extract_pitch_full import main
          main(["--input_folder", r"C:\data", "--output_folder", r"C:\out"])
"""

import argparse
import math
import os
import sys

try:
    import parselmouth
    from parselmouth.praat import call
except ImportError:  # pragma: no cover
    sys.exit(
        "This script needs parselmouth (Praat's engine for Python).\n"
        "Install it with:  pip install praat-parselmouth"
    )

# ---------------------------------------------------------------------------
# Defaults. Every one of these can be changed with a command-line argument.
# ---------------------------------------------------------------------------
OUTPUT_FOLDER = "pitch_output"
SUMMARY_FILENAME = "pitch_summary.txt"
CONTOUR_FILENAME = "pitch_contour_points.txt"
PHONES_TIER_NAME = "phones"
SYLL_TIER_NAME = "syll"
MAINWORDS_TIER_NAME = "mainwords"
WIDE_PASS_FLOOR = 60
WIDE_PASS_CEILING = 400
FLOOR_MULTIPLIER = 0.75
CEILING_MULTIPLIER = 2.5
POINTS_PER_WORD = 20
POINTS_PER_SYLLABLE = 10
POINTS_PER_VOWEL = 10

# Labels (space-separated) on the phones tier that count as vowels.
# The default is a SAMPA-like set for Brazilian Portuguese (~ = nasal);
# change it with --vowels to match YOUR annotation scheme.
VOWEL_SET = "a a~ E E~ e e~ i i~ O O~ o o~ u u~"
EPS = 0.002  # tolerance (s) when deciding if an interval lies inside another

SUMMARY_COLUMNS = [
    "file", "word", "wordStart_s", "wordEnd_s", "wordDur_s",
    "nSyll", "speakerMedianF0_Hz", "pitchFloor_Hz", "pitchCeiling_Hz",
    "wordVoicingProportion",
    "wordF0min_Hz", "wordF0min_time_s", "wordF0max_Hz", "wordF0max_time_s",
    "wordF0mean_Hz", "peakAlignment_inWord_norm",
    "valleyBeforePeak_Hz", "valleyBeforePeak_time_s",
    "valleyAfterPeak_Hz", "valleyAfterPeak_time_s",
    "riseVelocity_Hz_per_s", "riseVelocity_ST_per_s", "riseExcursion_ST",
    "fallVelocity_Hz_per_s", "fallVelocity_ST_per_s", "fallExcursion_ST",
    "syllIndex", "syllLabel", "syllStart_s", "syllEnd_s", "syllDur_s",
    "syllF0min_Hz", "syllF0max_Hz", "syllF0max_time_s", "syllF0mean_Hz",
    "peakAlignment_inSyll_norm",
    "vowelLabel", "vowelStart_s", "vowelEnd_s", "vowelDur_s",
    "vowelF0_onset_Hz", "vowelF0_offset_Hz", "vowelF0min_Hz", "vowelF0max_Hz",
    "vowelF0mean_Hz", "peakAlignment_inVowel_norm",
]

CONTOUR_COLUMNS = [
    "file", "word", "wordStart_s", "wordEnd_s",
    "level", "syllIndex", "syllLabel", "syllStart_s", "syllEnd_s",
    "vowelLabel", "vowelStart_s", "vowelEnd_s",
    "speakerMedianF0_Hz", "pitchFloor_Hz", "pitchCeiling_Hz",
    "pointIndex", "timeNorm", "time_s", "f0_Hz",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def undef(x):
    """Praat's 'undefined' comes back from parselmouth as NaN (or None here)."""
    return x is None or (isinstance(x, float) and math.isnan(x))


def fmt(x):
    """Praat: if undefined -> 'NA', else fixed$(x, 4)."""
    return "NA" if undef(x) else f"{x:.4f}"


def praat_round(x):
    """Praat's round(): half rounds up."""
    return math.floor(x + 0.5)


def warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr)


def in_span(s_start, s_end, outer_start, outer_end):
    """True if [s_start, s_end] lies inside [outer_start, outer_end] (within EPS)."""
    return s_start >= outer_start - EPS and s_end <= outer_end + EPS and s_end > s_start


def read_tier(textgrid, tier):
    """Return [(start, end, label), ...] for every interval of a tier."""
    n = int(call(textgrid, "Get number of intervals", tier))
    return [
        (
            call(textgrid, "Get start time of interval", tier, i),
            call(textgrid, "Get end time of interval", tier, i),
            call(textgrid, "Get label of interval", tier, i),
        )
        for i in range(1, n + 1)
    ]


def pitch_query(pitch, command, t1, t2):
    """Get minimum / maximum / time of ... (Hertz, Parabolic) over [t1, t2]."""
    return call(pitch, command, t1, t2, "Hertz", "Parabolic")


def sample_points(out, pitch, start_t, end_t, n, level, ctx, syll, vowel, spk):
    """
    Write n F0 samples evenly spaced across [start_t, end_t] to the contour file.

    ctx   = (base, wLabel, wStart$, wEnd$)
    syll  = (syllIndex$, syllLabel$, syllStart$, syllEnd$)
    vowel = (vowelLabel$, vowelStart$, vowelEnd$)
    spk   = (speakerMedianF0$, pFloor$, pCeiling$)
    """
    dur = end_t - start_t
    if dur <= 0:
        return
    for ip in range(1, n + 1):
        if n == 1:
            time_norm = 0.0
            t = start_t
        else:
            time_norm = (ip - 1) / (n - 1)
            t = start_t + time_norm * dur
        f0 = call(pitch, "Get value at time", t, "Hertz", "Linear")
        row = [*ctx, level, *syll, *vowel, *spk, str(ip), fmt(time_norm), fmt(t), fmt(f0)]
        out.write("\t".join(row) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None):
    args = parse_args(argv)
    input_folder = args.input_folder
    output_folder = args.output_folder
    vowel_set = set(args.vowels.split())

    if not os.path.isdir(input_folder):
        sys.exit(f"ERROR: input folder not found: {input_folder}")
    os.makedirs(output_folder, exist_ok=True)
    summary_path = os.path.join(output_folder, args.summary_filename)
    contour_path = os.path.join(output_folder, args.contour_filename)

    wavs = sorted(
        f for f in os.listdir(input_folder)
        if f.lower().endswith(".wav") and os.path.isfile(os.path.join(input_folder, f))
    )
    if not wavs:
        sys.exit(f"ERROR: no .wav files found in {input_folder}")
    n_done = 0

    with open(summary_path, "w", encoding="utf-8", newline="\n") as fsum, \
         open(contour_path, "w", encoding="utf-8", newline="\n") as fcon:

        fsum.write("\t".join(SUMMARY_COLUMNS) + "\n")
        fcon.write("\t".join(CONTOUR_COLUMNS) + "\n")

        for wav_name in wavs:
            base = wav_name[: wav_name.rindex(".")]

            tg_path = None
            for ext in (".TextGrid", ".textgrid"):
                candidate = os.path.join(input_folder, base + ext)
                if os.path.isfile(candidate):
                    tg_path = candidate
                    break
            if tg_path is None:
                warn(f"no TextGrid found for {base} - skipping")
                continue

            print(f"Processing {base} ...")
            try:
                sound = parselmouth.Sound(os.path.join(input_folder, wav_name))
                textgrid = call("Read from file", tg_path)
            except Exception as err:  # unreadable audio / malformed TextGrid
                warn(f"could not read {base} ({err}) - skipping")
                continue

            # --- locate tiers (last match wins, like the Praat loop) ---
            phones_tier = syll_tier = mainwords_tier = 0
            for t in range(1, int(call(textgrid, "Get number of tiers")) + 1):
                tname = call(textgrid, "Get tier name", t)
                if tname == args.phones_tier_name:
                    phones_tier = t
                elif tname == args.syll_tier_name:
                    syll_tier = t
                elif tname == args.mainwords_tier_name:
                    mainwords_tier = t

            if phones_tier == 0 or syll_tier == 0 or mainwords_tier == 0:
                warn(f"required tier(s) not found in {base} (looked for "
                     f"'{args.mainwords_tier_name}', '{args.syll_tier_name}', "
                     f"'{args.phones_tier_name}') - skipping")
                continue

            # --- two-pass pitch extraction (shared by both outputs) ---
            pitch_wide = call(sound, "To Pitch", 0, args.wide_pass_floor, args.wide_pass_ceiling)
            median_wide = call(pitch_wide, "Get quantile", 0, 0, 0.5, "Hertz")

            if undef(median_wide):
                p_floor = args.wide_pass_floor
                p_ceiling = args.wide_pass_ceiling
                warn(f"no voiced frames in wide pass for {base} - using the wide-pass range")
            else:
                p_floor = median_wide * args.floor_multiplier
                p_ceiling = median_wide * args.ceiling_multiplier

            pitch = call(sound, "To Pitch", 0, p_floor, p_ceiling)
            speaker_median = call(pitch, "Get quantile", 0, 0, 0.5, "Hertz")
            n_frames_total = int(call(pitch, "Get number of frames"))

            spk = (fmt(speaker_median), fmt(p_floor), fmt(p_ceiling))

            n_done += 1
            words = read_tier(textgrid, mainwords_tier)
            sylls = read_tier(textgrid, syll_tier)
            phones = read_tier(textgrid, phones_tier)

            for (w_start, w_end, w_label) in words:
                if w_label == "":
                    continue
                w_dur = w_end - w_start

                # --- word-level F0 measures ---
                w_f0min = pitch_query(pitch, "Get minimum", w_start, w_end)
                w_f0min_time = pitch_query(pitch, "Get time of minimum", w_start, w_end)
                w_f0max = pitch_query(pitch, "Get maximum", w_start, w_end)
                w_f0max_time = pitch_query(pitch, "Get time of maximum", w_start, w_end)
                w_f0mean = call(pitch, "Get mean", w_start, w_end, "Hertz")

                # --- voicing proportion ---
                f1 = call(pitch, "Get frame number from time", w_start)
                f2 = call(pitch, "Get frame number from time", w_end)
                f1r = praat_round(f1)
                f2r = praat_round(f2)
                if f1r < 1:
                    f1r = 1
                if f2r > n_frames_total:
                    f2r = n_frames_total
                voiced = total = 0
                if f2r >= f1r:
                    for fr in range(f1r, f2r + 1):
                        val = call(pitch, "Get value in frame", fr, "Hertz")
                        total += 1
                        if not undef(val):
                            voiced += 1
                voicing_prop = voiced / total if total > 0 else None

                # --- peak alignment in word ---
                if undef(w_f0max_time) or w_dur <= 0:
                    peak_align_word = None
                else:
                    peak_align_word = (w_f0max_time - w_start) / w_dur

                # --- valleys, rise / fall velocity and excursion ---
                valley_before_f0 = valley_before_time = None
                valley_after_f0 = valley_after_time = None
                rise_vel_hz = rise_vel_st = rise_exc_st = None
                fall_vel_hz = fall_vel_st = fall_exc_st = None

                if not undef(w_f0max_time):
                    if (w_f0max_time - w_start) > 0.005:
                        valley_before_f0 = pitch_query(pitch, "Get minimum", w_start, w_f0max_time)
                        valley_before_time = pitch_query(pitch, "Get time of minimum", w_start, w_f0max_time)
                        if not undef(valley_before_f0) and not undef(valley_before_time):
                            dt = w_f0max_time - valley_before_time
                            if dt > 0.005:
                                rise_vel_hz = (w_f0max - valley_before_f0) / dt
                                if valley_before_f0 > 0 and w_f0max > 0:
                                    rise_exc_st = 12 * math.log(w_f0max / valley_before_f0) / math.log(2)
                                    rise_vel_st = rise_exc_st / dt
                    if (w_end - w_f0max_time) > 0.005:
                        valley_after_f0 = pitch_query(pitch, "Get minimum", w_f0max_time, w_end)
                        valley_after_time = pitch_query(pitch, "Get time of minimum", w_f0max_time, w_end)
                        if not undef(valley_after_f0) and not undef(valley_after_time):
                            dt2 = valley_after_time - w_f0max_time
                            if dt2 > 0.005:
                                fall_vel_hz = (valley_after_f0 - w_f0max) / dt2
                                if valley_after_f0 > 0 and w_f0max > 0:
                                    fall_exc_st = 12 * math.log(valley_after_f0 / w_f0max) / math.log(2)
                                    fall_vel_st = fall_exc_st / dt2

                w_start_s = fmt(w_start)
                w_end_s = fmt(w_end)
                ctx = (base, w_label, w_start_s, w_end_s)
                NA3 = ("NA", "NA", "NA")
                NA4 = ("NA", "NA", "NA", "NA")

                # --- word-level contour points ---
                sample_points(fcon, pitch, w_start, w_end, args.points_per_word,
                              "word", ctx, NA4, NA3, spk)

                # --- syllables inside this word ---
                n_syll = sum(1 for (s0, s1, _) in sylls if in_span(s0, s1, w_start, w_end))

                syll_index = 0
                for (s_start, s_end, syll_label) in sylls:
                    if not in_span(s_start, s_end, w_start, w_end):
                        continue
                    syll_index += 1
                    syll_dur = s_end - s_start

                    sy_f0min = pitch_query(pitch, "Get minimum", s_start, s_end)
                    sy_f0max = pitch_query(pitch, "Get maximum", s_start, s_end)
                    sy_f0max_time = pitch_query(pitch, "Get time of maximum", s_start, s_end)
                    sy_f0mean = call(pitch, "Get mean", s_start, s_end, "Hertz")

                    if undef(w_f0max_time) or syll_dur <= 0:
                        peak_align_syll = None
                    else:
                        peak_align_syll = (w_f0max_time - s_start) / syll_dur

                    s_start_s = fmt(s_start)
                    s_end_s = fmt(s_end)
                    syll_index_s = str(syll_index)
                    syll_ctx = (syll_index_s, syll_label, s_start_s, s_end_s)

                    # --- syllable-level contour points ---
                    sample_points(fcon, pitch, s_start, s_end, args.points_per_syllable,
                                  "syllable", ctx, syll_ctx, NA3, spk)

                    # --- first vowel on phones tier inside this syllable ---
                    v_label = ""
                    v_start = v_end = None
                    found_vowel = False
                    for (p_start, p_end, p_label) in phones:
                        if in_span(p_start, p_end, s_start, s_end) and p_label in vowel_set:
                            v_label = p_label
                            v_start = p_start
                            v_end = p_end
                            found_vowel = True
                            break

                    v_dur = v_f0onset = v_f0offset = v_f0min = v_f0max = v_f0mean = None
                    peak_align_vowel = None
                    v_start_s = v_end_s = "NA"

                    if found_vowel:
                        v_dur = v_end - v_start
                        v_f0onset = call(pitch, "Get value at time", v_start, "Hertz", "Linear")
                        v_f0offset = call(pitch, "Get value at time", v_end, "Hertz", "Linear")
                        v_f0min = pitch_query(pitch, "Get minimum", v_start, v_end)
                        v_f0max = pitch_query(pitch, "Get maximum", v_start, v_end)
                        v_f0mean = call(pitch, "Get mean", v_start, v_end, "Hertz")
                        if not undef(w_f0max_time) and v_dur > 0:
                            peak_align_vowel = (w_f0max_time - v_start) / v_dur

                        v_start_s = fmt(v_start)
                        v_end_s = fmt(v_end)

                        # --- vowel-level contour points ---
                        sample_points(fcon, pitch, v_start, v_end, args.points_per_vowel,
                                      "vowel", ctx, syll_ctx, (v_label, v_start_s, v_end_s), spk)

                    if v_label == "":
                        v_label = "NA"

                    # --- assemble summary row ---
                    row = [
                        base, w_label, w_start_s, w_end_s, fmt(w_dur),
                        str(n_syll), *spk,
                        fmt(voicing_prop),
                        fmt(w_f0min), fmt(w_f0min_time), fmt(w_f0max), fmt(w_f0max_time),
                        fmt(w_f0mean), fmt(peak_align_word),
                        fmt(valley_before_f0), fmt(valley_before_time),
                        fmt(valley_after_f0), fmt(valley_after_time),
                        fmt(rise_vel_hz), fmt(rise_vel_st), fmt(rise_exc_st),
                        fmt(fall_vel_hz), fmt(fall_vel_st), fmt(fall_exc_st),
                        syll_index_s, syll_label, s_start_s, s_end_s, fmt(syll_dur),
                        fmt(sy_f0min), fmt(sy_f0max), fmt(sy_f0max_time), fmt(sy_f0mean),
                        fmt(peak_align_syll),
                        v_label, v_start_s, v_end_s, fmt(v_dur),
                        fmt(v_f0onset), fmt(v_f0offset), fmt(v_f0min), fmt(v_f0max),
                        fmt(v_f0mean), fmt(peak_align_vowel),
                    ]
                    fsum.write("\t".join(row) + "\n")

    print(f"Done. {n_done} of {len(wavs)} file(s) processed.")
    print("Done. Summary:", summary_path)
    print("Done. Contours:", contour_path)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Extract F0 summary + contour points from WAV/TextGrid pairs "
                    "(word, syllable and vowel level) using parselmouth.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input_folder", required=True,
                   help="folder with paired <name>.wav and <name>.TextGrid files")
    p.add_argument("--output_folder", default=OUTPUT_FOLDER, help="where to write the results")
    p.add_argument("--summary_filename", default=SUMMARY_FILENAME)
    p.add_argument("--contour_filename", default=CONTOUR_FILENAME)
    p.add_argument("--phones_tier_name", default=PHONES_TIER_NAME, help="segment tier")
    p.add_argument("--syll_tier_name", default=SYLL_TIER_NAME, help="syllable tier")
    p.add_argument("--mainwords_tier_name", default=MAINWORDS_TIER_NAME, help="word tier")
    p.add_argument("--vowels", default=VOWEL_SET,
                   help="space-separated phone labels to treat as vowels (quote the list)")
    p.add_argument("--wide_pass_floor", type=float, default=WIDE_PASS_FLOOR,
                   help="Hz; floor of the first (wide) pitch pass")
    p.add_argument("--wide_pass_ceiling", type=float, default=WIDE_PASS_CEILING,
                   help="Hz; ceiling of the first (wide) pitch pass")
    p.add_argument("--floor_multiplier", type=float, default=FLOOR_MULTIPLIER,
                   help="final pitch floor = this x the file's median F0")
    p.add_argument("--ceiling_multiplier", type=float, default=CEILING_MULTIPLIER,
                   help="final pitch ceiling = this x the file's median F0")
    p.add_argument("--points_per_word", type=int, default=POINTS_PER_WORD)
    p.add_argument("--points_per_syllable", type=int, default=POINTS_PER_SYLLABLE)
    p.add_argument("--points_per_vowel", type=int, default=POINTS_PER_VOWEL)
    return p.parse_args(argv)


if __name__ == "__main__":
    main()
