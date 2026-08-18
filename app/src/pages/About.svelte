<script lang="ts">
  import { locale, t } from "../lib/i18n";

  const isZh = $derived($locale === "zh-CN");

  interface MethodEntry {
    name: string;
    descZh: string;
    descEn: string;
    repo?: string;
    paperLabel?: string;
    paperUrl?: string;
    license: string;
  }

  const methods: MethodEntry[] = [
    {
      name: "Stanza",
      descZh: "斯坦福 NLP 组的官方 Python NLP 库，提供分词、词性标注、词形还原与依存句法分析（本项目 CoNLL-U 的来源）。",
      descEn: "Official Stanford NLP Python library for tokenization, POS tagging, lemmatization and dependency parsing (source of our CoNLL-U).",
      repo: "https://github.com/stanfordnlp/stanza",
      paperLabel: "Qi et al. (2020), ACL System Demonstrations",
      paperUrl: "https://arxiv.org/abs/2003.07082",
      license: "Apache-2.0",
    },
    {
      name: "QuanSyn",
      descZh: "定量句法分析包，本项目使用其 depval 模块计算 MHD、MV、VK、MTW、MTH、HI、HF、MTDL、MSL 等依存与配价指标。",
      descEn: "Quantitative syntax package; we use its depval module for MHD, MV, VK, MTW, MTH, HI, HF, MTDL, MSL dependency/valency metrics.",
      repo: "https://github.com/YuhuYang/QuanSyn",
      paperLabel: "Yang & Liu (2022), Europhysics Letters 139(6), 61002",
      license: "MIT",
    },
    {
      name: "NeoSCA",
      descZh: "L2SCA 句法复杂度分析器的现代化实现（基于 Java + Stanford Parser/Tregex），输出 MLS/MLT/MLC 等 L2SCA 系列指标。",
      descEn: "Modern L2SCA implementation (Java + Stanford Parser/Tregex) producing MLS/MLT/MLC and the other L2SCA indices.",
      repo: "https://github.com/tanloong/neosca",
      paperLabel: "Lu (2010), International Journal of Corpus Linguistics 15(4), 474–496",
      paperUrl: "https://doi.org/10.1075/ijcl.15.4.02lu",
      license: "GPL-3.0",
    },
    {
      name: "LeoDDcalculator",
      descZh: "提出 MDD/NDD 标准化依存距离公式的 R 包。注意：本项目并未调用该 R 包。",
      descEn: "The R package that proposed the MDD/NDD normalized dependency distance formulas. Note: this project does NOT call the R package.",
      repo: "https://github.com/leileibama/leoDDcalculator",
      paperLabel: "Lei & Jockers (2020), Journal of Quantitative Linguistics 27(1) · Lei & Wen (2020), Lingua 102762",
      paperUrl: "https://researchr.org/publication/LeiJ20",
      license: "R 包无明确开源协议（公式见论文）",
    },
    {
      name: "UDPipe",
      descZh: "底层依存句法分析器（C++），供 LeoDD 指标的 Python 复刻使用。",
      descEn: "Underlying dependency parser (C++) used by our Python reimplementation of the LeoDD metrics.",
      repo: "https://github.com/ufal/udpipe",
      paperLabel: "Straka & Straková (2017), CoNLL Shared Task",
      paperUrl: "https://aclanthology.org/K17-3009/",
      license: "代码 MPL-2.0；EWT 模型 CC BY-NC-SA",
    },
    {
      name: "MHDD（平均层级依存距离）",
      descZh: "本项目自定义实现的自有指标（基于 BFS 层级），与 AlphaDepLength 共同构成层级维度。",
      descEn: "Our own hierarchical metric (BFS-based), alongside AlphaDepLength, forming the hierarchical dimension.",
      paperLabel: "Chen & Deng (2021), Journal of Quantitative Linguistics",
      paperUrl: "https://doi.org/10.1080/09296174.2021.2005960",
      license: "指标定义（无软件实现）",
    },
  ];
</script>

<section class="page-section">
  <h2>{$t("nav.about")}</h2>
  <div class="about-brand">SynSpectra</div>
  <p class="muted">{$t("about.subtitle")}</p>

  <div class="card">
    <p>{$t("about.description")}</p>
  </div>

  <div class="card">
    <h3 class="card-title">{$t("about.authors")}</h3>
    <p class="about-authors">{$t("about.authorsValue")}</p>
    <p class="muted small">{$t("about.school")}</p>
  </div>

  <div class="card">
    <h3 class="card-title">{$t("about.project")}</h3>
    <div class="path-row">
      <span class="path-label">{$t("about.project")}</span>
      <a class="about-link" href="https://github.com/duanjiangDJ/synspectra" target="_blank" rel="noreferrer">
        https://github.com/duanjiangDJ/synspectra
      </a>
    </div>
    <div class="path-row">
      <span class="path-label">{$t("about.license")}</span>
      <a class="about-link" href="https://github.com/duanjiangDJ/synspectra/blob/main/LICENSE" target="_blank" rel="noreferrer">
        {$t("about.licenseValue")}
      </a>
    </div>
  </div>

  <div class="card">
    <h3 class="card-title">{$t("about.methods")}</h3>
    {#each methods as method (method.name)}
      <div class="about-method">
        <div class="about-method-head">
          <strong>{method.name}</strong>
          <span class="status-tag neutral">{method.license}</span>
        </div>
        <p class="muted small">{isZh ? method.descZh : method.descEn}</p>
        <div class="about-method-links">
          {#if method.repo}
            <a class="about-link" href={method.repo} target="_blank" rel="noreferrer">GitHub</a>
          {/if}
          {#if method.paperUrl}
            <a class="about-link" href={method.paperUrl} target="_blank" rel="noreferrer">{method.paperLabel}</a>
          {:else if method.paperLabel}
            <span class="muted small">{method.paperLabel}</span>
          {/if}
        </div>
      </div>
    {/each}
  </div>

  <div class="card">
    <h3 class="card-title">{$t("about.leoNoteTitle")}</h3>
    <p class="small">{isZh ? $t("about.leoNoteZh") : $t("about.leoNoteEn")}</p>
  </div>
</section>
