// Analysis languages offered by the UI. Every entry mirrors one profile in
// metric_modules/config.py: keep stanzaDir / leoModelFile / neosca in sync
// with LANGUAGE_PROFILES so the readiness checks match what the backend loads.

export interface LanguageOption {
  id: string;
  labelKey: string;
  /** Sub-directory under data_dir/stanza_resources holding this language's models. */
  stanzaDir: string;
  /** UDPipe model file name under data_dir/models. */
  leoModelFile: string;
  /** Whether the L2SCA/NeoSCA measures apply to this language. */
  neosca: boolean;
}

export const LANGUAGE_OPTIONS: LanguageOption[] = [
  {
    id: "en",
    labelKey: "language.en",
    stanzaDir: "en",
    leoModelFile: "english-ewt-ud-2.4-190531.udpipe",
    neosca: true,
  },
  {
    id: "zh",
    labelKey: "language.zh",
    stanzaDir: "zh-hans",
    leoModelFile: "chinese-gsd-ud-2.4-190531.udpipe",
    neosca: false,
  },
];

export function languageOption(id: string): LanguageOption {
  return LANGUAGE_OPTIONS.find((item) => item.id === id) ?? LANGUAGE_OPTIONS[0];
}

/** Distinct languages used by the given categories, falling back to the default. */
export function languagesInUse(
  categories: { name: string }[],
  languageFor: (category: string) => string,
  defaultLanguage: string,
): string[] {
  const used = new Set<string>();
  for (const category of categories) {
    used.add(languageFor(category.name));
  }
  if (used.size === 0) {
    used.add(defaultLanguage);
  }
  return [...used];
}

export function stanzaModelDir(stanzaRoot: string, language: string): string {
  return stanzaRoot.replace(/[\\/]+$/, "") + "/" + languageOption(language).stanzaDir;
}

export function leoModelPath(modelsDir: string, language: string): string {
  return modelsDir.replace(/[\\/]+$/, "") + "/" + languageOption(language).leoModelFile;
}
