import type { TranslationKey } from "@/i18n/types";

export type DossierDepth = "basic" | "standard" | "deep";

export type DepthOption = {
  id: DossierDepth;
  labelKey: TranslationKey;
  descKey: TranslationKey;
  /** Línea corta tiempo + beneficio (sin jerga de módulos). */
  metaKey: TranslationKey;
  credits: number;
  etaSeconds: number;
  modules: string[];
};

export const DEPTH_OPTIONS: DepthOption[] = [
  {
    id: "basic",
    labelKey: "depth.option_basic_label",
    descKey: "depth.option_basic_desc",
    metaKey: "depth.option_basic_meta",
    credits: 1,
    // Informe beta: medido hasta ~1 min; el pipeline es el mismo en las tres profundidades.
    etaSeconds: 45,
    modules: ["A"],
  },
  {
    id: "standard",
    labelKey: "depth.option_standard_label",
    descKey: "depth.option_standard_desc",
    metaKey: "depth.option_standard_meta",
    credits: 3,
    etaSeconds: 50,
    modules: ["A", "B"],
  },
  {
    id: "deep",
    labelKey: "depth.option_deep_label",
    descKey: "depth.option_deep_desc",
    metaKey: "depth.option_deep_meta",
    credits: 5,
    etaSeconds: 60,
    modules: ["A", "B", "C"],
  },
];
