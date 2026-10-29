# python-formants-extract

Extract formants (F1–F3 and bandwidths) from labelled intervals in a Praat TextGrid and plot the vowel space, all in Python. It is meant as a replacement for the usual Praat "formants at the vowel midpoint" script.

It uses [Parselmouth](https://parselmouth.readthedocs.io/), which runs Praat's own algorithms, so the measurements come from the same formant tracker you already know.

## What's in this repo

| File | What it does |
|---|---|
| `extract_formants.py` | Reads `.wav` + `.TextGrid` pairs and writes one CSV row per token |
| `plot_vowel_space.py` | Reads that CSV and draws an F1/F2 vowel plot with ellipses |
| `requirements.txt` | Python packages needed |

## Installation

```
pip install -r requirements.txt
```

## Preparing your data

Put your files in one folder (subfolders are fine). Each `.wav` needs a TextGrid with **the same name**:

```
data/
├── speaker1.wav
├── speaker1.TextGrid
├── speaker2.wav
└── speaker2.TextGrid
```

The TextGrid needs a tier whose intervals are labelled with the vowels you want to measure (for example a `phones` tier with labels like `a`, `e`, `i`).

## Usage

### Option 1: Spyder (Run button)

1. Open `extract_formants.py`.
2. Edit the `DEFAULT_ARGS` list at the top: the folder path, the tier name and the vowel labels.
3. Press **Run**. A file called `formants.csv` is created.
4. Open `plot_vowel_space.py`, check that `DEFAULT_ARGS` points to your CSV, and press **Run**. The plot is saved as `vowel_space.png`.

### Option 2: command line

```
python extract_formants.py data/ --tier phones --vowels a,e,i,o,u -o formants.csv
python plot_vowel_space.py formants.csv -o vowels.png
```

More examples:

```
# measure at 25%, 50% and 75% of each vowel
python extract_formants.py data/ --tier phones --vowels a,e,i,o,u --points 0.25 0.5 0.75

# choose the formant ceiling automatically for each file
python extract_formants.py data/ --tier phones --vowels a,e,i,o,u --auto-ceiling

# add the word each vowel belongs to (from another tier)
python extract_formants.py data/ --tier phones --word-tier words --vowels a,e,i,o,u

# select labels with a regular expression instead of a list
python extract_formants.py data/ --tier phones --regex "[aeiou][0-9]?"

# one plot panel per speaker/file
python plot_vowel_space.py formants.csv --facet-by file -o vowels.png
```

## Options: `extract_formants.py`

| Option | Default | Meaning |
|---|---|---|
| `folder` | – | Folder with `.wav` and `.TextGrid` files |
| `--tier` | – (required) | Tier name or number with the vowel intervals |
| `--word-tier` | none | Tier whose label is added as a `word` column |
| `--vowels` | all non-empty labels | Comma-separated labels to keep |
| `--regex` | – | Keep labels that fully match this pattern (alternative to `--vowels`) |
| `--points` | `0.5` | Positions inside each interval (0 = start, 1 = end) |
| `--min-dur` | `0.03` | Skip intervals shorter than this (seconds) |
| `--ceiling` | `5500` | Maximum formant in Hz (around 5000 for men, 5500 for women) |
| `--auto-ceiling` | off | Pick the ceiling per file (see below) |
| `--n-formants` | `5` | Number of formants Praat looks for |
| `--window` | `0.025` | Analysis window length (seconds) |
| `-o` | `formants.csv` | Output file |

### How `--auto-ceiling` works

A wrong formant ceiling is one of the most common causes of bad formant tracks. With this option the script tries ceilings from 4500 to 6500 Hz (step 250) on each file. For each one it measures F1 and F2 at the midpoint of every token and calculates how much each vowel scatters. The ceiling with the least scatter is used, and it is saved in the `ceiling` column. It needs at least two tokens per vowel in a file to work well.

## Output columns

| Column | Meaning |
|---|---|
| `file` | Name of the wav file |
| `interval` | Interval number on the tier |
| `label` | Vowel label |
| `prev`, `next` | Labels of the neighbouring intervals |
| `start`, `end`, `dur_ms` | Time boundaries (s) and duration (ms) |
| `ceiling` | Formant ceiling used (Hz) |
| `word` | Word label (only with `--word-tier`) |
| `F1_50`, `F2_50`, `F3_50` | Formants in Hz at 50% of the interval |
| `B1_50`, `B2_50`, `B3_50` | Bandwidths in Hz at 50% of the interval |

With `--points 0.25 0.5 0.75` you get the same columns ending in `_25`, `_50` and `_75`. Values that Praat cannot estimate are left empty (`NaN`).

## Options: `plot_vowel_space.py`

| Option | Default | Meaning |
|---|---|---|
| `csv` | – | CSV produced by `extract_formants.py` |
| `-o` | `vowel_space.png` | Output image (`.png`, `.pdf`, `.svg`) |
| `--point` | `50` | Which measurement point to plot (uses `F1_50` / `F2_50`) |
| `--facet-by` | none | Column to split into one panel per value (e.g. `file`) |
| `--min-count` | `3` | Ignore vowels with fewer tokens than this |

Ellipses show one standard deviation around each vowel's mean. Axes are inverted, as is conventional in phonetics.

## Tips

- Always check a sample of tokens against Praat's formant display. Automatic tracking makes errors, especially for high vowels, nasalized vowels and creaky voice.
- Check that the tier name and the vowel labels in your command match your TextGrids exactly (they are case-sensitive).

## Requirements

Python 3.9 or newer, plus the packages in `requirements.txt`.
