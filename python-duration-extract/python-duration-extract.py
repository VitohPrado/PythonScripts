# -*- coding: utf-8 -*-
"""
Extração de dados de duração e acústicos a partir de pares TextGrid + WAV.
Tradução para Python (parselmouth) do script Praat original.

@author: VitorPrado
"""

#%% 0. IMPORTAÇÕES E DEPENDÊNCIAS
import os
import glob
import pandas as pd
import parselmouth
from parselmouth.praat import call
from tqdm import tqdm

#%% 1. CONFIGURAÇÕES DE DIRETÓRIOS E PARÂMETROS
# IMPORTANTE: Instale as dependências antes de rodar:
# pip install praat-parselmouth pandas tqdm

# Diretório onde estão os arquivos .wav e .TextGrid
DIRETORIO_BASE = "C:/Caminho/Para/Sua/Pasta/De/Dados"

ORTHO_TIER = 6
WORD_TIER = 4
SYLL_TIER = 2
SEG_TIER = 1

EXTRAIR_FORMANTES = False
# Use 5500 para vozes femininas/infantis e 5000 para vozes masculinas
FREQUENCIA_MAXIMA_FORMANTES = 5500

FORMANT_FRACTIONS = [0.75, 0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20]

# Garante formatação correta de caminho
if not DIRETORIO_BASE.endswith(("/", "\\")):
    DIRETORIO_BASE += "/"

resultfile = os.path.join(DIRETORIO_BASE, "all_extracted_data.txt")

#%% 2. MONTAGEM DO CABEÇALHO (HEADER)
header = ["part", "ortholabel", "seglabel", "sylllabel", "wordlabel",
          "segdur", "sylldur", "worddur", "sentdur", "intmeanamp", "intmaxamp"]

if EXTRAIR_FORMANTES:
    for frac in FORMANT_FRACTIONS:
        pct = int(round(frac * 100))
        header += [f"p{pct}f1", f"p{pct}f2", f"p{pct}f3"]

rows = []

#%% 3. MAPEAMENTO DOS ARQUIVOS TEXTGRID
textgrid_files = sorted(glob.glob(os.path.join(DIRETORIO_BASE, "*.TextGrid")))
n_textgrids = len(textgrid_files)

if n_textgrids == 0:
    raise FileNotFoundError("Não existem arquivos .TextGrid na pasta informada!")

#%% 4. EXTRAÇÃO ACÚSTICA E DE DURAÇÃO (LOOP PRINCIPAL)
for ifile, tg_path in enumerate(tqdm(textgrid_files, desc="Processando TextGrids", unit="arq"), start=1):
    curr_file = os.path.basename(tg_path)
    sn = os.path.splitext(curr_file)[0]          # Nome do objeto (= "part")

    wav_file = sn + ".wav"
    wav_path = os.path.join(DIRETORIO_BASE, wav_file)

    # Imprime mensagem sem quebrar a barra de progresso do tqdm
    tqdm.write(f"Lendo arquivo {ifile}/{n_textgrids}: {curr_file}")

    textgrid = call("Read from file", tg_path)
    sound = call("Read from file", wav_path)

    formant = None
    if EXTRAIR_FORMANTES:
        formant = call(sound, "To Formant (burg)", 0, 5,
                       FREQUENCIA_MAXIMA_FORMANTES, 0.025, 50)

    numint = call(textgrid, "Get number of intervals", WORD_TIER)
    numint2 = numint - 1

    for i in range(1, numint2 + 1):
        wordlabel = call(textgrid, "Get label of interval", WORD_TIER, i)

        if wordlabel not in ("", "_"):
            wordstart = call(textgrid, "Get start time of interval", WORD_TIER, i)
            wordend = call(textgrid, "Get end time of interval", WORD_TIER, i)
            worddur = wordend - wordstart

            firstsyll = call(textgrid, "Get high interval at time", SYLL_TIER, wordstart)
            sylllabel = call(textgrid, "Get label of interval", SYLL_TIER, firstsyll)
            syllstart = wordstart
            syllend = call(textgrid, "Get end time of interval", SYLL_TIER, firstsyll)

            nsyll = firstsyll
            sylldur = syllend - syllstart

            numortho = call(textgrid, "Get interval at time", ORTHO_TIER, wordstart)
            ortholabel = call(textgrid, "Get label of interval", ORTHO_TIER, numortho)
            sentstart = call(textgrid, "Get start time of interval", ORTHO_TIER, numortho)
            sentend = call(textgrid, "Get end time of interval", ORTHO_TIER, numortho)
            sentdur = sentend - sentstart

            # --- percorre as sílabas da palavra ---
            while syllend <= wordend:

                firstseg = call(textgrid, "Get high interval at time", SEG_TIER, syllstart)
                seglabel = call(textgrid, "Get label of interval", SEG_TIER, firstseg)
                segstart = syllstart
                segend = call(textgrid, "Get end time of interval", SEG_TIER, firstseg)

                nseg = firstseg
                segdur = segend - segstart

                # Formantes: calculados 1x por sílaba, a partir do primeiro segmento
                formant_values = []
                if EXTRAIR_FORMANTES:
                    for frac in FORMANT_FRACTIONS:
                        tp = segstart + (segdur * frac)
                        f1 = call(formant, "Get value at time", 1, tp, "Hertz", "Linear")
                        f2 = call(formant, "Get value at time", 2, tp, "Hertz", "Linear")
                        f3 = call(formant, "Get value at time", 3, tp, "Hertz", "Linear")
                        formant_values += [f1, f2, f3]

                # Amplitude: calculada 1x por sílaba (primeiro segmento)
                intmeanamp = call(sound, "Get mean", 0, segstart, segend)
                intmaxamp = call(sound, "Get maximum", segstart, segend, "Sinc70")

                # --- percorre os segmentos da sílaba ---
                while segend <= syllend:
                    row = [sn, ortholabel, seglabel, sylllabel, wordlabel,
                           segdur, sylldur, worddur, sentdur,
                           intmeanamp, intmaxamp]
                    if EXTRAIR_FORMANTES:
                        row += formant_values
                    rows.append(row)

                    nseg += 1
                    seglabel = call(textgrid, "Get label of interval", SEG_TIER, nseg)
                    segstart = call(textgrid, "Get start time of interval", SEG_TIER, nseg)
                    segend = call(textgrid, "Get end time of interval", SEG_TIER, nseg)
                    segdur = segend - segstart

                nsyll += 1
                sylllabel = call(textgrid, "Get label of interval", SYLL_TIER, nsyll)
                syllstart = call(textgrid, "Get start time of interval", SYLL_TIER, nsyll)
                syllend = call(textgrid, "Get end time of interval", SYLL_TIER, nsyll)
                sylldur = syllend - syllstart

#%% 5. EXPORTAÇÃO DOS DADOS
df = pd.DataFrame(rows, columns=header)
df.to_csv(resultfile, sep="\t", index=False, encoding="utf-16-be")

print(f"\nProcessamento concluído com sucesso! {len(df)} linhas salvas em: {resultfile}")
