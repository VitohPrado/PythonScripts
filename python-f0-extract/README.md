# praat-f0-extractor

*[Read in English](README_eng.md)*

Extrai medidas de F0 (pitch) de **TextGrids + arquivos WAV do Praat** em três níveis — **palavra, sílaba e vogal** — e gera duas tabelas separadas por tabulação, prontas para usar no R ou no Python. Roda sobre o [Parselmouth](https://parselmouth.readthedocs.io/), então o rastreamento de pitch e todas as medidas usam o próprio motor do Praat; não é preciso abrir o Praat.

Foi escrito originalmente para analisar F0 e acento no português brasileiro, mas os nomes das camadas, os rótulos de vogais e os parâmetros de pitch são configuráveis.

## O que você obtém

| Arquivo | Conteúdo |
|---|---|
| `pitch_summary.txt` | Uma linha por **sílaba**. As medidas da palavra se repetem em cada linha de sílaba da palavra. |
| `pitch_contour_points.txt` | Formato longo: F0 amostrado em pontos de tempo normalizado em cada **palavra**, **sílaba** e **vogal** (coluna `level`). |

## Instalação

Requer Python 3.8+.

```bash
git clone https://github.com/<seu-usuario>/praat-f0-extractor.git
cd praat-f0-extractor
pip install -r requirements.txt
```

## Entrada

Uma pasta com pares de arquivos de mesmo nome:

```
data/
├── falante01_enun01.wav
├── falante01_enun01.TextGrid
├── falante01_enun02.wav
└── falante01_enun02.TextGrid
```

Cada TextGrid precisa de três **camadas de intervalo** (nomes configuráveis):

| Camada (nome padrão) | Conteúdo |
|---|---|
| `mainwords` | As palavras a analisar. Intervalos vazios são ignorados. |
| `syll` | Sílabas. Uma sílaba pertence a uma palavra se estiver dentro dela. |
| `phones` | Segmentos. Em cada sílaba, o **primeiro** intervalo cujo rótulo esteja em `--vowels` é a vogal. |

Arquivos sem TextGrid correspondente, ou sem as três camadas, são pulados com um aviso.

## Uso

```bash
python extract_pitch_full.py --input_folder data --output_folder results
```

Opções úteis (veja `python extract_pitch_full.py --help` para todas):

```bash
python extract_pitch_full.py \
  --input_folder data --output_folder results \
  --mainwords_tier_name palavras --syll_tier_name silabas --phones_tier_name segmentos \
  --vowels "a e i o u" \
  --points_per_word 30 --points_per_syllable 10 --points_per_vowel 10
```

**Spyder / Jupyter**:

```python
from extract_pitch_full import main
main(["--input_folder", r"C:\caminho\para\data", "--output_folder", r"C:\caminho\para\results"])
```

### Teste com o exemplo

A pasta `example/` tem uma gravação sintética curta da palavra "casa" (duas sílabas):

```bash
python extract_pitch_full.py --input_folder example --output_folder demo_output
```

Você deve obter 2 linhas em `pitch_summary.txt` (uma por sílaba) e 60 linhas em `pitch_contour_points.txt` (20 pontos da palavra + 2×10 de sílaba + 2×10 de vogal).

## Como o F0 é medido

1. **Rastreamento de pitch em duas passadas** (`To Pitch` do Praat, passo de tempo automático). Primeiro uma passada ampla (padrão 60–400 Hz) dá o F0 mediano do arquivo. A passada final usa uma faixa derivada dele: piso = `0,75 × mediana`, teto = `2,5 × mediana` (`--floor_multiplier`, `--ceiling_multiplier`). A faixa usada fica registrada na saída (`pitchFloor_Hz`, `pitchCeiling_Hz`).
2. **Mínimos, máximos e seus tempos**: em Hertz, com interpolação parabólica.
3. **Médias**: em Hertz.
4. **Pontos de contorno**: igualmente espaçados no trecho, incluindo as duas bordas (`timeNorm` de 0 a 1), com interpolação linear. Pontos não vozeados ficam `NA`.

> **Verifique os parâmetros de pitch para os seus dados.** Os valores padrão foram escolhidos para um conjunto específico de falantes e gravações. Inspecione os contornos (por exemplo, no Praat) e ajuste antes de confiar nos números.

## Colunas de saída

Valores indefinidos aparecem como `NA`. Todos os tempos estão em segundos.

**Resumo: nível da palavra** (repetido por sílaba): `file`, `word`, `wordStart_s`, `wordEnd_s`, `wordDur_s`, `nSyll`, `speakerMedianF0_Hz`, `pitchFloor_Hz`, `pitchCeiling_Hz`, `wordVoicingProportion` (frames de pitch vozeados / todos os frames da palavra), `wordF0min_Hz`/`_time_s`, `wordF0max_Hz`/`_time_s`, `wordF0mean_Hz`, `peakAlignment_inWord_norm` (tempo do pico relativo ao início da palavra, como proporção da duração da palavra).

**Resumo: subida e descida** (em relação ao pico de F0 da palavra):
- `valleyBeforePeak_*`: menor F0 entre o início da palavra e o pico. `valleyAfterPeak_*`: menor F0 entre o pico e o fim da palavra.
- `riseExcursion_ST` = 12·log₂(pico / vale anterior). `riseVelocity_Hz_per_s` / `_ST_per_s` = excursão dividida pelo tempo entre o vale e o pico.
- `fallExcursion_ST` e `fallVelocity_*` são calculados em direção ao vale posterior ao pico, portanto são **negativos**.
- Os vales ficam `NA` quando o pico está a menos de 5 ms da borda da palavra; excursão e velocidade ficam `NA` quando o vale está a menos de 5 ms do pico.

**Resumo: nível da sílaba**: `syllIndex` (posição na palavra), `syllLabel`, `syllStart_s`, `syllEnd_s`, `syllDur_s`, `syllF0min_Hz`, `syllF0max_Hz`, `syllF0max_time_s`, `syllF0mean_Hz`, `peakAlignment_inSyll_norm`.

**Resumo: nível da vogal** (primeira vogal da sílaba): `vowelLabel`, `vowelStart_s`, `vowelEnd_s`, `vowelDur_s`, `vowelF0_onset_Hz`, `vowelF0_offset_Hz`, `vowelF0min_Hz`, `vowelF0max_Hz`, `vowelF0mean_Hz`, `peakAlignment_inVowel_norm`.

`peakAlignment_inSyll_norm` e `_inVowel_norm` localizam o pico de F0 **da palavra** em relação à sílaba ou vogal: 0 = início, 1 = fim; valores abaixo de 0 ou acima de 1 indicam que o pico cai antes ou depois dela.

**Arquivo de contorno**: `file`, `word`, `wordStart_s`, `wordEnd_s`, `level` (`word` / `syllable` / `vowel`), identificadores de sílaba e vogal (`NA` onde não se aplicam), `speakerMedianF0_Hz`, `pitchFloor_Hz`, `pitchCeiling_Hz`, `pointIndex`, `timeNorm`, `time_s`, `f0_Hz`.

## Comportamentos conhecidos

- Uma palavra sem nenhuma sílaba dentro dela na camada `syll` **não gera linha** em `pitch_summary.txt` (os pontos de contorno da palavra ainda são escritos).
- Sílabas sem vogal de `--vowels` ficam com `NA` nas colunas de vogal e sem pontos de contorno de vogal.
- Para ler os resultados no R: `read.delim("pitch_summary.txt", na.strings = "NA", fileEncoding = "UTF-8")`.

## Citação

Se usar em pesquisa, cite também o Praat e o Parselmouth:

- Boersma, P. & Weenink, D. *Praat: doing phonetics by computer* [Programa de computador]. https://www.praat.org
- Jadoul, Y., Thompson, B., & de Boer, B. (2018). Introducing Parselmouth: A Python interface to Praat. *Journal of Phonetics, 71*, 1–15.

## Licença

MIT — veja [LICENSE](LICENSE). O Parselmouth e o Praat têm licenças próprias (GPL).

