# 多维句法复杂度分析整合包

一个用于计算英语文本多维句法复杂度指标的综合 Python 工具包。该工具包整合了四种主要计算方法——基于公式自设计的计算流程（下称自定义）、QuanSyn、NeoSCA 和 LeoDDcalculator 公式的 Python 复刻（基于 UDPipe 模型），为定量句法分析提供了统一、可复现的计算流程。

## 目录

- [概述](#概述)
- [计算的指标](#计算的指标)
- [项目结构](#项目结构)
- [运行时文件结构](#运行时文件结构)
- [依赖与安装](#依赖与安装)
  - [1. Python 环境](#1-python-环境)
  - [2. Stanza](#2-stanza)
  - [3. QuanSyn](#3-quansyn)
  - [4. NeoSCA](#4-neosca)
  - [5. UDPipe 与 LeoDD Python 复刻](#5-udpipe-与-leodd-python-复刻)
  - [6. Python 标准库](#6-python-标准库)
- [通过 requirements.txt 快速安装](#通过-requirementstxt-快速安装)
- [使用方法](#使用方法)
- [输出文件](#输出文件)
- [脚本说明](#脚本说明)
- [断点续传](#断点续传)
- [引用本项目](#引用本项目)
- [许可证](#许可证)

---

## 概述

本工具包为每篇英语文本计算超过 40 项句法复杂度指标，涵盖以下维度：

- **依存距离**（线性与层级）：MDD、MHDD、NDD、AlphaDepLength
- **QuanSyn** 指标组：MHD、TDL、SL、MV、VK、HI、HF、MTW、MTH、MTDL、MSL
- **NeoSCA**（L2SCA 系列）指标：MLS、MLT、MLC、C/S、VP/T、C/T、DC/C、DC/T、T/S、CT/T、CP/T、CP/C、CN/T、CN/C，以及 9 项结构频次统计（W、S、VP、C、T、DC、CT、CP、CN）
- **LeoDDcalculator**（Lei & Jockers, 2018）：MDD_Leo、NDD_Leo
- **QuanSyn** 的 MDD/NDD：MDD_quansyn、NDD_quansyn

由于在实践过程中发现各工具对于部分指标的计算方式较为不同，此工具包将不同的计算方式整合以便于比对研究，该工具包专为按文件夹组织的文本语料批量处理而设计，内置断点续传功能，可稳健处理大规模分析任务。

---

## 计算的指标

| 类别                   | 指标                                                         | 来源工具                 |
| ---------------------- | ------------------------------------------------------------ | ------------------------ |
| 依存距离（线性）       | MDD、NDD                                                     | 自定义 + LeoDD + QuanSyn |
| 依存距离（层级）       | MHDD、AlphaDepLength                                         | 自定义（基于 BFS）       |
| QuanSyn（depval 模块） | MHD、TDL、SL、MV、VK、HI、HF、MTW、MTH、MTDL、MSL、MDD_quansyn、NDD_quansyn | QuanSyn                  |
| L2SCA 句法复杂度       | MLS、MLT、MLC、C/S、VP/T、C/T、DC/C、DC/T、T/S、CT/T、CP/T、CP/C、CN/T、CN/C | NeoSCA                   |
| 结构频次               | W、S、VP、C、T、DC、CT、CP、CN                               | NeoSCA                   |

---

## 项目结构

```
project-root/
├── source/                              # 输入数据目录
│ └── category_name/                     # 每个类别一个子文件夹（内含 .txt 文件）
│     ├── sample1.txt
│     ├── sample2.txt
│     └── ...
├── result/                              # 输出目录（自动创建）
│ └── category_name.csv                  # 每个类别的最终 CSV 文件
├── run_metrics.py                       # 统一入口：按配置或命令行启用/禁用计算方法
├── metrics_config.json                   # 计算方法、输出列和路径配置
├── metric_modules/                       # 模块化计算实现
├── requirements.txt                     # Python 依赖
└── README.md                            # 本文件
```

---

## 运行时文件结构

运行流程前，请按以下方式组织输入数据：

```
source/
├── group_A/
│ ├── essay_01.txt
│ ├── essay_02.txt
│ └── ...
├── group_B/
│ ├── report_01.txt
│ └── ...
└── ...
```

- **`source/`** 是顶级数据目录（自动检测，位于脚本所在目录）。
- `source/` 下的每个子文件夹（如 `group_A`）代表一个文本**类别**。
- 所有 `.txt` 文件直接放在类别文件夹内（例如 `source/group_A/essay_01.txt`）。
- 每个 `.txt` 文件被视为一个独立样本。
- 输出 CSV（如 `result/group_A.csv`）将包含每个 `.txt` 文件一行，所有计算指标作为列。

---

## 依赖与安装

### 1. Python 环境

**要求：** Python 3.8 或更高版本。

```bash
python --version
```

强烈建议使用**虚拟环境**：

```bash
# 创建虚拟环境
python -m venv venv

# 激活（Windows）
venv\Scripts\activate

# 激活（macOS/Linux）
source venv/bin/activate
```

---

### 2. Stanza

**官方仓库：** [https://github.com/stanfordnlp/stanza](https://github.com/stanfordnlp/stanza)  
**官方文档：** [https://stanfordnlp.github.io/stanza/](https://stanfordnlp.github.io/stanza/)

Stanza 是斯坦福 NLP 组的官方 Python NLP 库，支持 60 多种语言。它通过神经网络流程提供分词、词性标注、词形还原和依存句法分析功能。

**安装：**

```bash
pip install stanza
```

Stanza 依赖 PyTorch 1.2.0 或更高版本。

**下载英文模型（首次使用前必须执行）：**

```python
import stanza
stanza.download('en')  # 下载神经网络流程的英文模型
```

此步骤将下载约 500 MB 的模型文件至 `~/stanza_resources/`。如果使用 Jupyter notebook，请使用 `stanza.download('en', force=True)` 跳过确认提示。

---

### 3. QuanSyn

**PyPI：** [https://pypi.org/project/quansyn/](https://pypi.org/project/quansyn/)  
**GitHub：** [https://github.com/YuhuYang/QuanSyn](https://github.com/YuhuYang/QuanSyn)

QuanSyn 是一个用于定量句法分析的 Python 包。包含三个模块：`depval`（依存与配价指标）、`lawfitter`（分布拟合）和 `lingnet`（复杂网络构建）。本项目使用 `depval` 模块。

**安装：**

```bash
pip install quansyn
```

QuanSyn 需要 `nltk` 和 `conllu` 作为依赖：

```bash
pip install nltk conllu
```

---

### 4. NeoSCA

**PyPI：** [https://pypi.org/project/neosca/](https://pypi.org/project/neosca/)  
**GitHub：** [https://github.com/tanloong/neosca](https://github.com/tanloong/neosca)

NeoSCA 是 L2 句法复杂度分析器（L2SCA）的现代化实现，其内部依赖 Java 运行 Stanford Parser 与 Tregex。

#### 4.1 安装JAVA

NeoSCA依赖java而运行，因此在安装NeoSCA之前，你需要安装java（jdk）。要求jdk版本为8及以上，此处推荐jdk17，你可以通过[该链接](https://www.oracle.com/java/technologies/javase/jdk17-archive-downloads.html)进入官网获取jdk17，或通过[该链接](https://download.oracle.com/java/17/archive/jdk-17.0.12_windows-x64_bin.msi)直接下载jdk17的安装程序。

安装完成后，对于Windows系统，你需要确认环境变量“JAVA_HOME”已配置为jdk的安装路径，随后重启电脑。尝试在终端或CMD输入以下命令
```bash
java -version
```
若可查询java版本信息则安装成功。

#### 4.2 安装 NeoSCA及其依赖

首先，在终端中运行以下命令安装NeoSCA：
```bash
# 在你的终端中运行以下命令
pip install neosca

# 安装完成后，输入该命令安装依赖
nsca --check-depends
```
若此处要求你安装java，则上一步的java未安装完成，请检查安装步骤是否完成。若java安装成功，则此处会下载安装Stanford Parser与Stanford Tregex。

完成后请自行准备一个txt文件，在终端中进入文件所在文件夹并输入以下命令尝试运行neosca：
```bash
python -m neosca filepath.txt # 此处filepath.txt为文件名称
```
若能正常运行，且运行后在同目录下生成了result.csv文件，说明NeoSCA已准备完毕。

---

### 5. UDPipe 与 LeoDD Python 复刻

本项目已将原先通过 R 包 `leoDDcalculator` 调用的 `mdd_ndd_calculate()` 逻辑复刻到 Python 模块 `metric_modules/leo_dd.py` 中。主流程不再需要安装 R、Rtools、R 包或 `rpy2`。

Python 复刻版仍使用 LeoDDcalculator 原函数相同的 UDPipe 英文模型与公式：每句排除 `root` 与 `punct` 依存关系后计算 MDD，并使用 `abs(log(mdd / sqrt(sent_length * root_distance)))` 计算 NDD。

**安装 Python 绑定：**

```bash
pip install ufal.udpipe
```

#### 5.1 下载 UDPipe 英文语言模型

下载 `UDPipe` 的英文语言模型：

- **模型文件：** `english-ewt-ud-2.4-190531.udpipe`
- **下载链接：** [https://github.com/jwijffels/udpipe.models.ud.2.4/blob/master/inst/udpipe-ud-2.4-190531/english-ewt-ud-2.4-190531.udpipe](https://github.com/jwijffels/udpipe.models.ud.2.4/blob/master/inst/udpipe-ud-2.4-190531/english-ewt-ud-2.4-190531.udpipe)

将下载的 `.udpipe` 文件放置到 **C 盘根目录**（`C:/`），默认完整路径为 `C:/english-ewt-ud-2.4-190531.udpipe`。如有需要，可在 `metrics_config.json` 的 `leo.language_model_folder` 中自定义模型目录。

---

### 6. Python 标准库

以下第三方库会通过 `requirements.txt` 安装：

```bash
pip install pandas ufal.udpipe
```

其余依赖（`os`、`re`、`csv`、`math`、`tempfile`、`subprocess`、`shutil`、`collections`）均为 Python 标准库的一部分，无需额外安装。

---

## 通过 requirements.txt 快速安装

所有 Python 依赖可通过一条命令安装：

```bash
pip install -r requirements.txt
```

**安装完 Python 包后**，仍需完成以下步骤：

1. 在 Python 中运行 `stanza.download('en')` 以下载 Stanza 英文模型。
2. 下载 UDPipe 英文模型并放置到 `C:/english-ewt-ud-2.4-190531.udpipe`（参见上文第 5 节）。
3. 如需计算 NeoSCA 指标，安装 Java 并运行 `nsca --check-depends`。

---

## 使用方法

### 1. 准备输入数据

按照[运行时文件结构](#运行时文件结构)中的说明，将 `.txt` 文件组织到 `source/<类别>/` 目录下。

### 2. 配置 UDPipe 模型路径

默认路径为 `C:/english-ewt-ud-2.4-190531.udpipe`。如果模型放在其他位置，请在 `metrics_config.json` 的 `leo.language_model_folder` 中修改模型目录。

### 3. 选择启用的计算方法

统一入口为 `run_metrics.py`。默认读取 `metrics_config.json`，可在 `methods` 中自由启用或禁用各计算方法：

```json
{
  "methods": {
    "custom": true,
    "leo": true,
    "quansyn": true,
    "neosca": false
  }
}
```

如果只想输出部分列，可同步调整 `output_fields`。默认配置与当前 `result/text.csv` 一致：启用自定义、LeoDD Python 复刻和 QuanSyn，关闭 NeoSCA。

使用统一入口运行：

```bash
python run_metrics.py --config metrics_config.json
```

也可以不修改配置，直接使用命令行预设或方法列表：

```bash
python run_metrics.py --preset other   # 自定义 + LeoDD Python 复刻 + QuanSyn
python run_metrics.py --preset all     # 启用全部方法
python run_metrics.py --preset neosca  # 仅 NeoSCA，输出后缀为 _NeoSCA
python run_metrics.py --methods custom,leo,quansyn --no-resume
```

脚本将：
- 遍历 `source/` 下的每个子文件夹。
- 对每个 `.txt` 文件，清洗文本并计算所有指标。
- 逐步将结果写入 `result/<类别名称>.csv`。
- 支持断点续传：如果运行中断，重新运行将自动跳过已处理的文件；如需强制重算可使用 `--no-resume`。

---

## 输出文件

结果保存在 `result/` 目录中，以 CSV 文件形式存储：

```
result/
├── group_A.csv
├── group_B.csv
└── ...
```

每个 CSV 包含以下列：

| 列名                                             | 描述                                             | 来源       |
| ------------------------------------------------ | ------------------------------------------------ | ---------- |
| `filename`                                       | 输入 `.txt` 文件名                               | —          |
| `MHDD`                                           | 平均层级依存距离                                 | 自定义     |
| `AlphaDepLength`                                 | Alpha 依存长度                                   | 自定义     |
| `MDD`                                            | 平均依存距离（自定义实现）                       | 自定义     |
| `NDD`                                            | 标准化依存距离（自定义实现）                     | 自定义     |
| `MDD_Leo`                                        | 按 LeoDDcalculator 公式复刻计算的 MDD             | LeoDD Python 复刻 |
| `NDD_Leo`                                        | 按 LeoDDcalculator 公式复刻计算的 NDD             | LeoDD Python 复刻 |
| `MDD_quansyn`                                    | QuanSyn 计算的 MDD                               | QuanSyn    |
| `NDD_quansyn`                                    | QuanSyn 计算的 NDD                               | QuanSyn    |
| `MHD`                                            | 平均层级距离                                     | QuanSyn    |
| `MV`                                             | 平均配价                                         | QuanSyn    |
| `VK`                                             | 动词关键度                                       | QuanSyn    |
| `MTW`                                            | 平均树宽                                         | QuanSyn    |
| `MTH`                                            | 平均树高                                         | QuanSyn    |
| `HI`                                             | 中心节点指数                                     | QuanSyn    |
| `HF`                                             | 中心节点频率                                     | QuanSyn    |
| `MTDL`                                           | 平均总依存长度                                   | QuanSyn    |
| `MSL`                                            | 平均句长                                         | QuanSyn    |
| `MLS`、`MLT`、`MLC`                              | 平均句子 / T 单位 / 子句长度                     | NeoSCA     |
| `C/S`、`VP/T`、`C/T`                             | 每句子子句数 / 每 T 单位 VP 数 / 每 T 单位子句数 | NeoSCA     |
| `DC/C`、`DC/T`                                   | 每子句从属子句数 / 每 T 单位从属子句数           | NeoSCA     |
| `T/S`                                            | 每句子 T 单位数                                  | NeoSCA     |
| `CT/T`、`CP/T`、`CP/C`、`CN/T`、`CN/C`           | 复杂 T 单位 / 并列短语 / 复杂名词比例            | NeoSCA     |
| `W`、`S`、`VP`、`C`、`T`、`DC`、`CT`、`CP`、`CN` | 结构频次统计                                     | NeoSCA     |

---

## 脚本说明

| 脚本                         | 描述                                                         | 依赖                                               |
| ---------------------------- | ------------------------------------------------------------ | -------------------------------------------------- |
| `run_metrics.py`             | 根目录唯一 Python 入口，按配置、预设或 `--methods` 启用/禁用计算方法 | 取决于配置启用项                                  |
| `metrics_config.json`        | 默认配置：路径、断点续传、输出列、计算方法开关                 | —                                                  |
| `metric_modules/`            | 自定义、LeoDD、QuanSyn、NeoSCA、管线调度等模块化实现           | Stanza、QuanSyn、NeoSCA、ufal.udpipe              |

---

## 断点续传

所有脚本均支持**断点续传**功能：

- 已处理的文件名记录在输出 CSV 中。
- 如果执行中断（如断电、崩溃），只需重新运行脚本——它将自动检测已处理的文件并从上次中断处继续。
- LeoDD Python 复刻结果会被缓存并在多次运行中复用。**切勿擅自删除运行中的leo结果文件夹（如果你不知道一个文件夹为什么突然出现在那里，那最好别碰）**

---

## 引用本项目

如果您在研究中使用本工具包，请引用本项目以及所使用的底层工具及其相关论文：

**本论文：**

>

**Stanza：**

> Qi, P., Zhang, Y., Zhang, Y., Bolton, J., & Manning, C. D. (2020). Stanza: A Python Natural Language Processing Toolkit for Many Human Languages. *Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics: System Demonstrations*.

**QuanSyn：**

> Yang, M., & Liu, H. (2022). The role of syntax in the formation of scale-free language networks. *Europhysics Letters*, 139(6), 61002.

**NeoSCA：**

> Lu, X. (2010). Automatic analysis of syntactic complexity in second language writing. *International Journal of Corpus Linguistics*, 15(4), 474–496.

**LeoDDcalculator（MDD/NDD）：**

> Lei, L., & Jockers, M. L. (2018). Normalized Dependency Distance: Proposing a New Measure. *Journal of Quantitative Linguistics*, 1–18.

> Lei, L., & Wen, J. (2019). Is dependency distance experiencing a process of minimization? A diachronic study based on the State of the Union addresses. *Lingua*, 102762.

**MHDD：**

> Chen, R., & Deng, S. (2021). Syntactic Complexity of Different Text Types: From the Perspective of Dependency Distance Both Linearly and Hierarchically. *Journal of Quantitative Linguistics*.


---

## 许可证

本项目采用 **GPL 3.0 License**。您可以在`LICENSE`中查看更多细节。

请注意：本项目使用的依赖项受其各自许可证的约束：

- **Stanza：** Apache 2.0
- **QuanSyn：** MIT
- **NeoSCA：** GPL 3.0
- **leoDDcalculator 公式复刻：** 请同时引用 LeoDDcalculator 相关论文
- **ufal.udpipe / UDPipe：** 请参考其上游许可证与模型许可证
