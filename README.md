# PythonScripts

Python replacements for common Praat scripts used in phonetic research. Each folder is a self-contained tool: it reads your `.wav` and `.TextGrid` files, writes a CSV, and needs no Praat scripting.

Everything uses [Parselmouth](https://parselmouth.readthedocs.io/), a Python interface to Praat's own algorithms, so the measurements come from the same analyses you would run in Praat.

## Scripts

| Folder | What it does |
|---|---|
| [`python-duration-extract`](python-duration-extract) | Extracts durations of labelled intervals from TextGrids |
| [`python-f0-extract`](python-f0-extract) | Extracts F0 (pitch) values from labelled intervals |
| [`python-formants-extract`](python-formants-extract) | Extracts F1–F3 and bandwidths, with automatic formant ceiling, and plots the vowel space |

Each folder has its own README with usage instructions and options.

## Getting started

1. Install Python 3.9 or newer.
2. Download or clone this repository:
   ```
   git clone https://github.com/VitohPrado/PythonScripts.git
   ```
3. Install the packages for the script you want to use (each folder has a `requirements.txt`):
   ```
   pip install -r python-formants-extract/requirements.txt
   ```
4. Follow the README inside the folder.

## Typical input

Put your files in one folder, with a TextGrid of the same name next to each recording:

```
data/
├── speaker1.wav
├── speaker1.TextGrid
├── speaker2.wav
└── speaker2.TextGrid
```

## Author

Vitor Prado, PhD student in Linguistics at UFMG (Brazilian Portuguese phonology and phonetics).

Questions or suggestions are welcome through the Issues tab.
