# praat-f0-extractor

*[Leia em português](README.pt-BR.md)*

Extract F0 (pitch) measures from **Praat TextGrids + WAV files** at three levels — **word, syllable and vowel** — and get two tidy, tab-separated tables ready for R or Python. It runs on [Parselmouth](https://parselmouth.readthedocs.io/), so pitch tracking and every measurement use Praat's own engine; no need to open Praat.

Originally written to analyse F0 and stress in Brazilian Portuguese, but the tier names, vowel labels and pitch settings are all configurable.

## What you get

| File | Content |
|---|---|
| `pitch_summary.txt` | One row per **syllable**. Word-level measures are repeated on each syllable row of the word. |
| `pitch_contour_points.txt` | Long format: F0 sampled at time-normalised points over each **word**, **syllable** and **vowel** (column `level`). |

## Installation

Requires Python 3.8+.

```bash
git clone https://github.com/<your-user>/praat-f0-extractor.git
cd praat-f0-extractor
pip install -r requirements.txt
```

## Input

A folder with paired files sharing the same name:

```
data/
├── speaker01_utt01.wav
├── speaker01_utt01.TextGrid
├── speaker01_utt02.wav
└── speaker01_utt02.TextGrid
```

Each TextGrid needs three **interval tiers** (names configurable):

| Tier (default name) | What it holds |
|---|---|
| `mainwords` | The words to analyse. Empty intervals are ignored. |
| `syll` | Syllables. A syllable belongs to a word if it lies inside it. |
| `phones` | Segments. In each syllable, the **first** interval whose label is in `--vowels` is the vowel. |

Files without a matching TextGrid, or without all three tiers, are skipped with a warning.

## Usage

```bash
python extract_pitch_full.py --input_folder data --output_folder results
```

Useful options (see `python extract_pitch_full.py --help` for all):

```bash
python extract_pitch_full.py \
  --input_folder data --output_folder results \
  --mainwords_tier_name words --syll_tier_name syllables --phones_tier_name segments \
  --vowels "a e i o u" \
  --points_per_word 30 --points_per_syllable 10 --points_per_vowel 10
```

**Spyder / Jupyter**:

```python
from extract_pitch_full import main
main(["--input_folder", r"C:\path\to\data", "--output_folder", r"C:\path\to\results"])
```

### Try it with the demo

`example/` has a tiny synthetic recording of the word "casa" (two syllables):

```bash
python extract_pitch_full.py --input_folder example --output_folder demo_output
```

You should get 2 rows in `pitch_summary.txt` (one per syllable) and 60 rows in `pitch_contour_points.txt` (20 word + 2×10 syllable + 2×10 vowel points).

## How F0 is measured

1. **Two-pass pitch tracking** (Praat's `To Pitch`, automatic time step). First a wide pass (default 60–400 Hz) gives the file's median F0. The final pass uses a range derived from it: floor = `0.75 × median`, ceiling = `2.5 × median` (`--floor_multiplier`, `--ceiling_multiplier`). The range used is saved in the output (`pitchFloor_Hz`, `pitchCeiling_Hz`).
2. **Minima, maxima and their times**: Hertz, parabolic interpolation.
3. **Means**: in Hertz.
4. **Contour points**: evenly spaced over the span, both edges included (`timeNorm` from 0 to 1), linear interpolation. Unvoiced points are `NA`.

> **Check the pitch settings for your data.** The defaults were chosen for one specific set of speakers and recordings. Inspect the tracks (e.g. in Praat) and adjust before trusting the numbers.

## Output columns

Undefined values are written as `NA`. All times are in seconds.

**Summary: word level** (repeated per syllable): `file`, `word`, `wordStart_s`, `wordEnd_s`, `wordDur_s`, `nSyll`, `speakerMedianF0_Hz`, `pitchFloor_Hz`, `pitchCeiling_Hz`, `wordVoicingProportion` (voiced pitch frames / all frames in the word), `wordF0min_Hz`/`_time_s`, `wordF0max_Hz`/`_time_s`, `wordF0mean_Hz`, `peakAlignment_inWord_norm` (peak time relative to word start, as a proportion of word duration).

**Summary: rise and fall** (relative to the word's F0 peak):
- `valleyBeforePeak_*`: lowest F0 between word start and the peak. `valleyAfterPeak_*`: lowest F0 between the peak and word end.
- `riseExcursion_ST` = 12·log₂(peak / valley before). `riseVelocity_Hz_per_s` / `_ST_per_s` = excursion divided by the time between the valley and the peak.
- `fallExcursion_ST` and `fallVelocity_*` are computed toward the valley after the peak, so they are **negative**.
- Valleys are `NA` when the peak is within 5 ms of the word edge; excursion and velocity are `NA` when the valley is within 5 ms of the peak.

**Summary: syllable level**: `syllIndex` (position in the word), `syllLabel`, `syllStart_s`, `syllEnd_s`, `syllDur_s`, `syllF0min_Hz`, `syllF0max_Hz`, `syllF0max_time_s`, `syllF0mean_Hz`, `peakAlignment_inSyll_norm`.

**Summary: vowel level** (first vowel of the syllable): `vowelLabel`, `vowelStart_s`, `vowelEnd_s`, `vowelDur_s`, `vowelF0_onset_Hz`, `vowelF0_offset_Hz`, `vowelF0min_Hz`, `vowelF0max_Hz`, `vowelF0mean_Hz`, `peakAlignment_inVowel_norm`.

`peakAlignment_inSyll_norm` and `_inVowel_norm` locate the **word's** F0 peak relative to that syllable or vowel: 0 = start, 1 = end, and values below 0 or above 1 mean the peak falls before or after it.

**Contour file**: `file`, `word`, `wordStart_s`, `wordEnd_s`, `level` (`word` / `syllable` / `vowel`), syllable and vowel identifiers (`NA` where they don't apply), `speakerMedianF0_Hz`, `pitchFloor_Hz`, `pitchCeiling_Hz`, `pointIndex`, `timeNorm`, `time_s`, `f0_Hz`.

## Known behaviours

- A word with no syllable inside it on the `syll` tier produces **no row** in `pitch_summary.txt` (its word-level contour points are still written).
- Syllables with no vowel from `--vowels` get `NA` in the vowel columns, and no vowel contour points.
- Reading the results in R: `read.delim("pitch_summary.txt", na.strings = "NA", fileEncoding = "UTF-8")`.

## Citation

If you use this in research, please also cite Praat and Parselmouth:

- Boersma, P. & Weenink, D. *Praat: doing phonetics by computer* [Computer program]. https://www.praat.org
- Jadoul, Y., Thompson, B., & de Boer, B. (2018). Introducing Parselmouth: A Python interface to Praat. *Journal of Phonetics, 71*, 1–15.

## License

MIT — see [LICENSE](LICENSE). Parselmouth and Praat have their own licenses (GPL).
