# Multidimensional Syntactic Complexity Analyzer

A comprehensive Python toolkit for computing multidimensional syntactic complexity metrics of English texts. This toolkit integrates four major computational approaches — custom formula-based implementations, **QuanSyn**, **NeoSCA**, and a Python reimplementation of the **LeoDDcalculator** formula using UDPipe — to provide a unified, reproducible pipeline for quantitative syntactic analysis.

## Table of Contents

- [Overview](#overview)
- [Metrics Computed](#metrics-computed)
- [Project Structure](#project-structure)
- [File Structure (Runtime)](#file-structure-runtime)
- [Dependencies & Installation](#dependencies--installation)
  - [1. Python Environment](#1-python-environment)
  - [2. Stanza](#2-stanza)
  - [3. QuanSyn](#3-quansyn)
  - [4. NeoSCA](#4-neosca)
  - [5. UDPipe and LeoDD Python Reimplementation](#5-udpipe-and-leodd-python-reimplementation)
  - [6. Python Standard Libraries](#6-python-standard-libraries)
- [Quick Install via requirements.txt](#quick-install-via-requirementstxt)
- [Usage](#usage)
- [Output Files](#output-files)
- [Scripts Description](#scripts-description)
- [Resume from Breakpoint](#resume-from-breakpoint)
- [Citing This Project](#citing-this-project)
- [License](#license)

---

## Overview

This toolkit computes over 40 syntactic complexity metrics for each English text, spanning the following dimensions:

- **Dependency Distance** (linear & hierarchical): MDD, MHDD, NDD, AlphaDepLength
- **QuanSyn** suite: MHD, TDL, SL, MV, VK, HI, HF, MTW, MTH, MTDL, MSL
- **NeoSCA** (L2SCA-family) indices: MLS, MLT, MLC, C/S, VP/T, C/T, DC/C, DC/T, T/S, CT/T, CP/T, CP/C, CN/T, CN/C, plus 9 structural frequency counts (W, S, VP, C, T, DC, CT, CP, CN)
- **LeoDDcalculator** (Lei & Jockers, 2018): MDD_Leo, NDD_Leo
- **QuanSyn** MDD/NDD: MDD_quansyn, NDD_quansyn

Since the various tools employ different implementations for certain metrics, this toolkit consolidates them into a single pipeline to facilitate comparative research. It is designed for batch processing of text corpora organized by category folders, with built-in checkpoint/resume functionality to handle large-scale analyses robustly.

---

## Metrics Computed

| Category | Metrics | Source Tool |
|---|---|---|
| Dependency Distance (linear) | MDD, NDD | Custom + LeoDD + QuanSyn |
| Dependency Distance (hierarchical) | MHDD, AlphaDepLength | Custom (BFS-based) |
| QuanSyn (depval) | MHD, TDL, SL, MV, VK, HI, HF, MTW, MTH, MTDL, MSL, MDD_quansyn, NDD_quansyn | QuanSyn |
| L2SCA Syntactic Complexity | MLS, MLT, MLC, C/S, VP/T, C/T, DC/C, DC/T, T/S, CT/T, CP/T, CP/C, CN/T, CN/C | NeoSCA |
| Structural Frequencies | W, S, VP, C, T, DC, CT, CP, CN | NeoSCA |

---

## Project Structure

```
project-root/
├── source/                              # Input data directory
│   └── category_name/                   # One subfolder per category (contains .txt files)
│       ├── sample1.txt
│       ├── sample2.txt
│       └── ...
├── result/                              # Output directory (auto-created)
│   └── category_name.csv                # Final CSV per category
├── calculate_all_metrics.py             # Main script: combined pipeline
├── calculate_other_metrics.py           # Standalone: Custom + QuanSyn + LeoDD
├── calculate_neosca.py                  # Standalone: NeoSCA only
├── leo_dd_python.py                      # Python reimplementation of LeoDDcalculator
├── requirements.txt                     # Python dependencies
└── README.md                            # This file
```

---

## File Structure (Runtime)

Before running the pipeline, organize your input data as follows:

```
source/
├── group_A/
│   ├── essay_01.txt
│   ├── essay_02.txt
│   └── ...
├── group_B/
│   ├── report_01.txt
│   └── ...
└── ...
```

- **`source/`** is the top-level data directory (automatically detected; located in the same directory as the script).
- Each subfolder under `source/` (e.g., `group_A`) represents one **category** of texts.
- All `.txt` files are placed directly inside the category folder (e.g., `source/group_A/essay_01.txt`).
- Each `.txt` file is treated as one independent sample.
- The output CSV (e.g., `result/group_A.csv`) will contain one row per `.txt` file, with all computed metrics as columns.

---

## Dependencies & Installation

### 1. Python Environment

**Required:** Python 3.8 or later.

```bash
python --version
```

We strongly recommend using a **virtual environment**:

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate
```

---

### 2. Stanza

**Official Repository:** [https://github.com/stanfordnlp/stanza](https://github.com/stanfordnlp/stanza)  
**Official Documentation:** [https://stanfordnlp.github.io/stanza/](https://stanfordnlp.github.io/stanza/)

Stanza is the official Python NLP library from the Stanford NLP Group, supporting 60+ languages. It provides tokenization, POS tagging, lemmatization, and dependency parsing via neural pipelines.

**Installation:**

```bash
pip install stanza
```

Stanza requires PyTorch 1.2.0 or above as a dependency.

**Download English Models (required before first use):**

```python
import stanza
stanza.download('en')  # Downloads the English models for the neural pipeline
```

This step will download approximately 500 MB of model files to `~/stanza_resources/`. If using a Jupyter notebook, use `stanza.download('en', force=True)` to bypass the confirmation prompt.

---

### 3. QuanSyn

**PyPI:** [https://pypi.org/project/quansyn/](https://pypi.org/project/quansyn/)  
**GitHub:** [https://github.com/YuhuYang/QuanSyn](https://github.com/YuhuYang/QuanSyn)

QuanSyn is a Python package for quantitative syntax analysis. It includes three modules: `depval` (dependency and valency metrics), `lawfitter` (distribution fitting), and `lingnet` (complex network construction). This project uses the `depval` module.

**Installation:**

```bash
pip install quansyn
```

QuanSyn requires `nltk` and `conllu` as dependencies:

```bash
pip install nltk conllu
```

---

### 4. NeoSCA

**PyPI:** [https://pypi.org/project/neosca/](https://pypi.org/project/neosca/)  
**GitHub:** [https://github.com/tanloong/neosca](https://github.com/tanloong/neosca)

NeoSCA is a modern implementation of the L2 Syntactic Complexity Analyzer (L2SCA). It internally relies on Java to run Stanford Parser and Stanford Tregex.

#### 4.1 Install Java

NeoSCA depends on Java to function, so you need to install JDK before installing NeoSCA. JDK 8 or above is required; JDK 17 is recommended. You can visit [this link](https://www.oracle.com/java/technologies/javase/jdk17-archive-downloads.html) to obtain JDK 17 from the official website, or directly download the JDK 17 installer via [this link](https://download.oracle.com/java/17/archive/jdk-17.0.12_windows-x64_bin.msi).

After installation (for Windows), make sure the environment variable `JAVA_HOME` is set to the JDK installation path, then restart your computer. Try entering the following command in your terminal or CMD:

```bash
java -version
```

If Java version information is displayed, the installation was successful.

#### 4.2 Install NeoSCA and Its Dependencies

First, run the following command in your terminal to install NeoSCA:

```bash
pip install neosca
```

After installation, run the following command to install its dependencies:

```bash
nsca --check-depends
```

If this step prompts you to install Java, the previous Java installation step was not completed successfully. Please check the Java installation steps and try again. If Java is properly installed, this command will download and install Stanford Parser and Stanford Tregex.

Once complete, prepare a sample `.txt` file, navigate to the folder containing it in your terminal, and run:

```bash
python -m neosca filepath.txt  # Replace filepath.txt with your file name
```

If it runs successfully and a `result.csv` file is generated in the same directory, NeoSCA is ready to use.

---

### 5. UDPipe and LeoDD Python Reimplementation

This project now reimplements the original R package `leoDDcalculator` function `mdd_ndd_calculate()` in Python as `leo_dd_python.py`. The main scripts no longer require R, Rtools, R packages, or `rpy2`.

The Python version uses the same UDPipe English model and formula as the original function: it excludes `root` and `punct` dependencies when computing sentence-level MDD, then computes NDD with `abs(log(mdd / sqrt(sent_length * root_distance)))`.

**Install the Python binding:**

```bash
pip install ufal.udpipe
```

#### 5.1 Download the UDPipe English Language Model

Download the English language model for `UDPipe`:

- **Model file:** `english-ewt-ud-2.4-190531.udpipe`
- **Download URL:** [https://github.com/jwijffels/udpipe.models.ud.2.4/blob/master/inst/udpipe-ud-2.4-190531/english-ewt-ud-2.4-190531.udpipe](https://github.com/jwijffels/udpipe.models.ud.2.4/blob/master/inst/udpipe-ud-2.4-190531/english-ewt-ud-2.4-190531.udpipe)

Place the downloaded `.udpipe` file in the **root of your C: drive** (`C:/`), so the default full path is `C:/english-ewt-ud-2.4-190531.udpipe`. You may customize this path in `leo_dd_python.py` or when calling `calculate_folder_mdd_ndd()`.

---

### 6. Python Standard Libraries

The following third-party libraries are installed through `requirements.txt`:

```bash
pip install pandas ufal.udpipe
```

The remaining dependencies (`os`, `re`, `csv`, `math`, `tempfile`, `subprocess`, `shutil`, `collections`) are part of the Python standard library and require no additional installation.

---

## Quick Install via requirements.txt

All Python dependencies can be installed in one command:

```bash
pip install -r requirements.txt
```

**After installing the Python packages**, you still need to:

1. Run `stanza.download('en')` in Python to download the Stanza English models.
2. Download the UDPipe English model and place it at `C:/english-ewt-ud-2.4-190531.udpipe` (see Section 5 above).
3. If you need NeoSCA metrics, install Java and run `nsca --check-depends`.

---

## Usage

### 1. Prepare Input Data

Organize your `.txt` files under `source/<category>/` as described in [File Structure (Runtime)](#file-structure-runtime).

### 2. Configure the UDPipe Model Path

The default path is `C:/english-ewt-ud-2.4-190531.udpipe`. If you place the model elsewhere, update the path in `leo_dd_python.py` or in the call to `calculate_folder_mdd_ndd()`.

###  Calculate all metrics

```bash
python calculate_all_metrics.py
```

The script will:
- Traverse each subfolder under `source/`.
- For each `.txt` file, clean the text and compute all metrics.
- Write results progressively to `result/<category_name>.csv`.
- Support checkpoint/resume: if interrupted, rerunning will automatically skip already-processed files.

### 4. Running Standalone Scripts

If you only need a subset of metrics:

```bash
# Dependency metrics + QuanSyn + LeoDDcalculator
python calculate_other_metrics.py

# NeoSCA syntactic complexity only
python calculate_neosca.py
```

---

## Output Files

Results are saved in the `result/` directory as CSV files:

```
result/
├── group_A.csv
├── group_B.csv
└── ...
```

Each CSV contains the following columns:

| Column | Description | Source |
|---|---|---|
| `filename` | Name of the input `.txt` file | — |
| `MHDD` | Mean Hierarchical Dependency Distance | Custom |
| `AlphaDepLength` | Alpha Dependency Length | Custom |
| `MDD` | Mean Dependency Distance (custom implementation) | Custom |
| `NDD` | Normalized Dependency Distance (custom implementation) | Custom |
| `MDD_Leo` | MDD computed from the reimplemented LeoDDcalculator formula | LeoDD Python reimplementation |
| `NDD_Leo` | NDD computed from the reimplemented LeoDDcalculator formula | LeoDD Python reimplementation |
| `MDD_quansyn` | MDD computed by QuanSyn | QuanSyn |
| `NDD_quansyn` | NDD computed by QuanSyn | QuanSyn |
| `MHD` | Mean Hierarchical Distance | QuanSyn |
| `MV` | Mean Valency | QuanSyn |
| `VK` | Verb Keyness | QuanSyn |
| `MTW` | Mean Tree Width | QuanSyn |
| `MTH` | Mean Tree Height | QuanSyn |
| `HI` | Hub Index | QuanSyn |
| `HF` | Hub Frequency | QuanSyn |
| `MTDL` | Mean Total Dependency Length | QuanSyn |
| `MSL` | Mean Sentence Length | QuanSyn |
| `MLS`, `MLT`, `MLC` | Mean Length of Sentence / T-unit / Clause | NeoSCA |
| `C/S`, `VP/T`, `C/T` | Clauses per Sentence / VP per T-unit / Clauses per T-unit | NeoSCA |
| `DC/C`, `DC/T` | Dependent Clauses per Clause / T-unit | NeoSCA |
| `T/S` | T-units per Sentence | NeoSCA |
| `CT/T`, `CP/T`, `CP/C`, `CN/T`, `CN/C` | Complex T-unit / Coordinate Phrase / Complex Nominal ratios | NeoSCA |
| `W`, `S`, `VP`, `C`, `T`, `DC`, `CT`, `CP`, `CN` | Structural frequency counts | NeoSCA |

---

## Scripts Description

| Script | Description | Dependencies |
|---|---|---|
| `calculate_all_metrics.py` | **Main script.** Computes all metrics (custom + QuanSyn + NeoSCA + LeoDD) | Stanza, QuanSyn, NeoSCA, ufal.udpipe |
| `calculate_other_metrics.py` | Computes dependency-based metrics (custom), QuanSyn, and LeoDDcalculator metrics | Stanza, QuanSyn, ufal.udpipe |
| `calculate_neosca.py` | Computes only NeoSCA syntactic complexity metrics | NeoSCA |
| `leo_dd_python.py` | Reimplements the LeoDDcalculator MDD/NDD folder workflow | ufal.udpipe |

---

## Resume from Breakpoint

All scripts support **checkpoint/resume** functionality:

- Processed filenames are recorded in the output CSV.
- If execution is interrupted (e.g., power loss, crash), simply re-run the script — it will automatically detect already-processed files and continue from where it left off.
- LeoDDcalculator results are cached and reused across runs. **Do not delete the Leo results folder that appears during execution** (if you are unsure why a folder suddenly appeared, it is best to leave it alone).

---

## Citing This Project

If you use this toolkit in your research, please cite this project along with the underlying tools and their associated publications:

**This Paper:**

>

**Stanza:**

> Qi, P., Zhang, Y., Zhang, Y., Bolton, J., & Manning, C. D. (2020). Stanza: A Python Natural Language Processing Toolkit for Many Human Languages. *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics: System Demonstrations*.

**QuanSyn:**

> Yang, M., & Liu, H. (2022). The role of syntax in the formation of scale-free language networks. *Europhysics Letters*, 139(6), 61002.

**NeoSCA:**

> Lu, X. (2010). Automatic analysis of syntactic complexity in second language writing. *International Journal of Corpus Linguistics*, 15(4), 474–496.

**LeoDDcalculator (MDD/NDD):**

> Lei, L., & Jockers, M. L. (2018). Normalized Dependency Distance: Proposing a New Measure. *Journal of Quantitative Linguistics*, 1–18.

> Lei, L., & Wen, J. (2019). Is dependency distance experiencing a process of minimization? A diachronic study based on the State of the Union addresses. *Lingua*, 102762.

**MHDD:**

> Chen, R., & Deng, S. (2021). Syntactic Complexity of Different Text Types: From the Perspective of Dependency Distance Both Linearly and Hierarchically. *Journal of Quantitative Linguistics*.

---

## License

This project is licensed under the **GPL 3.0 License**. See the `LICENSE` file for more details.

Note: The dependencies used in this project are governed by their own licenses:

- **Stanza:** Apache 2.0
- **QuanSyn:** MIT
- **NeoSCA:** GPL 3.0
- **LeoDDcalculator formula reimplementation:** cite the LeoDDcalculator papers when using these columns
- **ufal.udpipe / UDPipe:** see the upstream package and model licenses
