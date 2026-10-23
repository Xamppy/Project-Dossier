"""Plantillas de prompts de dossier localizadas (corporativo y persona)."""
from __future__ import annotations

from dossier.services.output_language import normalize_output_language

_CORPORATE_DELIVERY: dict[str, str] = {
    "es": """
**Estilo:** redacción **breve y escaneable** (el cliente no debe aburrirse leyendo). Prioriza bullets y párrafos cortos; evita texto denso, repeticiones y subapartados innecesarios. Si un punto no aporta valor, omítelo.

**Estructura obligatoria del Markdown:**

1. **Resumen ejecutivo** — solo lo esencial (pocas viñetas o un párrafo corto).
2. **Riesgos o vacíos** — conciso; solo riesgos de negocio / cumplimiento (no meta-comentarios técnicos).
3. **Recomendación sobre relacionarse o hacer negocios** — antes de las preguntas. Indica de forma clara si **conviene** avanzar, **solo con condiciones/salvaguardas** o **no conviene** relacionarse con la contraparte según el análisis; una viñeta o dos como máximo con el porqué.
4. **Preguntas sugeridas para la reunión** — **entre 2 y 3 preguntas** (máximo 3), cada una en **una sola frase**.

Si el contexto es **solo Reino Unido** o **solo Estados Unidos**, el apartado 3 se refiere a esa única contraparte.
Si el contexto incluye **UK y USA** como entidades distintas, el apartado 3 debe separar la recomendación por jurisdicción (viñetas breves UK vs EE.UU.).
""".strip(),
    "en": """
**Style:** **brief, scannable** writing. Prefer bullets and short paragraphs; avoid dense text and repetition.

**Mandatory Markdown structure:**

1. **Executive summary** — essentials only (a few bullets or one short paragraph).
2. **Risks or gaps** — concise; business/compliance risks only (no technical meta-commentary).
3. **Recommendation on engaging or doing business** — before the questions. State clearly whether proceeding is **advisable**, **only with safeguards**, or **not advisable**, with one or two bullets explaining why.
4. **Suggested questions for the meeting** — **2 to 3 questions** (max 3), each in **one sentence**.

If the context is **UK-only** or **US-only**, section 3 refers to that single counterparty.
If both **UK and US** apply as distinct entities, section 3 must separate the recommendation by jurisdiction (brief UK vs US bullets).
""".strip(),
    "pt": """
**Estilo:** redação **breve e escaneável**. Priorize marcadores e parágrafos curtos.

**Estrutura obrigatória do Markdown:**

1. **Resumo executivo** — apenas o essencial.
2. **Riscos ou lacunas** — conciso; só riscos de negócio/conformidade.
3. **Recomendação sobre relacionar-se ou fazer negócios** — antes das perguntas. Indique claramente se **convém** avançar, **só com salvaguardas** ou **não convém**.
4. **Perguntas sugeridas para a reunião** — **2 a 3 perguntas** (máx. 3), cada uma em **uma frase**.

Se o contexto for só **Reino Unido** ou só **Estados Unidos**, o ponto 3 refere-se a essa contraparte única.
Se houver **UK e EUA** como entidades distintas, separe a recomendação por jurisdição.
""".strip(),
    "it": """
**Stile:** redazione **breve e scansionabile**. Preferisci elenchi e paragrafi corti.

**Struttura obbligatoria del Markdown:**

1. **Sommario esecutivo** — solo l'essenziale.
2. **Rischi o lacune** — conciso; solo rischi di business/compliance.
3. **Raccomandazione su relazione o affari** — prima delle domande. Indica chiaramente se **conviene** procedere, **solo con salvaguardie** o **non conviene**.
4. **Domande suggerite per la riunione** — **2-3 domande** (max 3), ciascuna in **una frase**.

Se il contesto è solo **Regno Unito** o solo **Stati Uniti**, il punto 3 riguarda quella controparte.
Se **UK e USA** sono entità distinte, separa la raccomandazione per giurisdizione.
""".strip(),
    "fr": """
**Style :** rédaction **brève et lisible**. Privilégiez puces et paragraphes courts.

**Structure Markdown obligatoire :**

1. **Résumé exécutif** — l'essentiel uniquement.
2. **Risques ou lacunes** — concis ; risques business/conformité seulement.
3. **Recommandation sur la relation ou les affaires** — avant les questions. Indiquez clairement si avancer est **recommandé**, **uniquement avec garanties** ou **déconseillé**.
4. **Questions suggérées pour la réunion** — **2 à 3 questions** (max 3), chacune en **une phrase**.

Si le contexte est **Royaume-Uni seul** ou **États-Unis seuls**, le point 3 concerne cette contrepartie.
Si **UK et USA** sont des entités distinctes, séparez la recommandation par juridiction.
""".strip(),
    "de": """
**Stil:** **kurze, gut scannbare** Darstellung. Bevorzugen Sie Aufzählungen und kurze Absätze.

**Pflichtstruktur des Markdown:**

1. **Zusammenfassung für die Geschäftsführung** — nur das Wesentliche (wenige Punkte oder ein kurzer Absatz).
2. **Risiken und Lücken** — knapp; nur Geschäfts- und Compliance-Risiken (keine technischen Meta-Kommentare).
3. **Empfehlung zur Zusammenarbeit oder Geschäftsbeziehung** — vor den Fragen. Klar angeben, ob ein Vorgehen **sinnvoll**, **nur mit Auflagen** oder **nicht sinnvoll** ist (max. ein bis zwei Punkte mit Begründung).
4. **Vorgeschlagene Fragen für das Meeting** — **2 bis 3 Fragen** (maximal 3), jeweils in **einem Satz**.

Bei Kontext **nur Vereinigtes Königreich** oder **nur USA** bezieht sich Punkt 3 auf diese eine Gegenpartei.
Bei **UK und USA** als getrennten Entitäten die Empfehlung nach Rechtsraum trennen (kurze UK- vs. US-Punkte).
""".strip(),
}

_CORPORATE_DUAL_NOTE: dict[str, str] = {
    "es": (
        "En el **resumen ejecutivo** (apartado 1), separa en bullets breves lo que aplica a "
        "**UK** y lo que aplica a **EE. UU.**, sin fusionar entidades."
    ),
    "en": (
        "In the **executive summary** (section 1), use brief bullets for what applies to "
        "**UK** vs **US**, without merging entities."
    ),
    "pt": (
        "No **resumo executivo** (secção 1), separe em marcadores o que se aplica ao "
        "**Reino Unido** e aos **EUA**, sem fundir entidades."
    ),
    "it": (
        "Nel **sommario esecutivo** (sezione 1), separa in elenchi ciò che riguarda **UK** e **USA**, "
        "senza fondere le entità."
    ),
    "fr": (
        "Dans le **résumé exécutif** (section 1), séparez en puces ce qui concerne le **Royaume-Uni** "
        "et les **É.-U.**, sans fusionner les entités."
    ),
    "de": (
        "In der **Zusammenfassung für die Geschäftsführung** (Abschnitt 1) trennen Sie in kurzen "
        "Aufzählungspunkten, was für das **UK** und was für die **USA** gilt, ohne Entitäten zu vermischen."
    ),
}

_SYSTEM_WRITING_LINE: dict[str, str] = {
    "en": "Write the **entire** dossier in **English**, in Markdown.",
    "pt": "Redija **todo** o dossiê em **português**, em Markdown.",
    "it": "Redigi **l'intero** dossier in **italiano**, in Markdown.",
    "fr": "Rédigez **l'intégralité** du dossier en **français**, en Markdown.",
    "de": "Verfassen Sie den **gesamten** Bericht auf **Deutsch**, in Markdown.",
}

# Sustituciones ordenadas (plantilla persona en español → idioma objetivo).
_PERSON_REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("DOSSIER EJECUTIVO", "EXECUTIVE DOSSIER"),
        ("## ESTRUCTURA OBLIGATORIA DEL DOSSIER", "## MANDATORY DOSSIER STRUCTURE"),
        ("### 1. FICHA DE IDENTIDAD", "### 1. IDENTITY CARD"),
        ("### 2. RESUMEN EJECUTIVO", "### 2. EXECUTIVE SUMMARY"),
        ("### 3. TRAYECTORIA PROFESIONAL", "### 3. PROFESSIONAL BACKGROUND"),
        ("### 4. PRESENCIA DIGITAL Y REPUTACIONAL", "### 4. DIGITAL AND REPUTATIONAL PRESENCE"),
        ("### 5. ANÁLISIS DE RIESGO", "### 5. RISK ANALYSIS"),
        ("### 6. VÍNCULOS EMPRESARIALES", "### 6. CORPORATE LINKS"),
        ("### 7. CONCLUSIÓN Y RECOMENDACIÓN", "### 7. CONCLUSION AND RECOMMENDATION"),
        ("### 8. FUENTES Y NIVEL DE CONFIANZA", "### 8. SOURCES AND CONFIDENCE LEVEL"),
        ("## REGLAS DE FORMATO", "## FORMAT RULES"),
        ("[OBSERVACIÓN]", "[OBSERVATION]"),
        ("[INCONSISTENCIA]", "[INCONSISTENCY]"),
        ("[ALERTA LEVE]", "[LOW ALERT]"),
        ("[ALERTA MODERADA]", "[MODERATE ALERT]"),
        ("[ALERTA CRÍTICA]", "[CRITICAL ALERT]"),
        ("[INFERENCIA]", "[INFERENCE]"),
        ("No disponible", "Not available"),
        ("Sin evidencia disponible", "No evidence available"),
        ("No aplica", "Not applicable"),
    ],
    "pt": [
        ("DOSSIER EJECUTIVO", "DOSSIÊ EXECUTIVO"),
        ("## ESTRUCTURA OBLIGATORIA DEL DOSSIER", "## ESTRUTURA OBRIGATÓRIA DO DOSSIÊ"),
        ("### 1. FICHA DE IDENTIDAD", "### 1. FICHA DE IDENTIDADE"),
        ("### 2. RESUMEN EJECUTIVO", "### 2. RESUMO EXECUTIVO"),
        ("### 3. TRAYECTORIA PROFESIONAL", "### 3. TRAJETÓRIA PROFISSIONAL"),
        ("### 4. PRESENCIA DIGITAL Y REPUTACIONAL", "### 4. PRESENÇA DIGITAL E REPUTACIONAL"),
        ("### 5. ANÁLISIS DE RIESGO", "### 5. ANÁLISE DE RISCO"),
        ("### 6. VÍNCULOS EMPRESARIALES", "### 6. VÍNCULOS EMPRESARIAIS"),
        ("### 7. CONCLUSIÓN Y RECOMENDACIÓN", "### 7. CONCLUSÃO E RECOMENDAÇÃO"),
        ("### 8. FUENTES Y NIVEL DE CONFIANZA", "### 8. FONTES E NÍVEL DE CONFIANÇA"),
        ("## REGLAS DE FORMATO", "## REGRAS DE FORMATAÇÃO"),
        ("[OBSERVACIÓN]", "[OBSERVAÇÃO]"),
        ("[INCONSISTENCIA]", "[INCONSISTÊNCIA]"),
        ("[ALERTA LEVE]", "[ALERTA LEVE]"),
        ("[ALERTA MODERADA]", "[ALERTA MODERADA]"),
        ("[ALERTA CRÍTICA]", "[ALERTA CRÍTICA]"),
        ("[INFERENCIA]", "[INFERÊNCIA]"),
        ("No disponible", "Não disponível"),
        ("Sin evidencia disponible", "Sem evidência disponível"),
        ("No aplica", "Não se aplica"),
    ],
    "it": [
        ("DOSSIER EJECUTIVO", "DOSSIER ESECUTIVO"),
        ("## ESTRUCTURA OBLIGATORIA DEL DOSSIER", "## STRUTTURA OBBLIGATORIA DEL DOSSIER"),
        ("### 1. FICHA DE IDENTIDAD", "### 1. SCHEDA IDENTITÀ"),
        ("### 2. RESUMEN EJECUTIVO", "### 2. SOMMARIO ESECUTIVO"),
        ("### 3. TRAYECTORIA PROFESIONAL", "### 3. PERCORSO PROFESSIONALE"),
        ("### 4. PRESENCIA DIGITAL Y REPUTACIONAL", "### 4. PRESENZA DIGITALE E REPUTAZIONALE"),
        ("### 5. ANÁLISIS DE RIESGO", "### 5. ANALISI DEL RISCHIO"),
        ("### 6. VÍNCULOS EMPRESARIALES", "### 6. LEGAMI AZIENDALI"),
        ("### 7. CONCLUSIÓN Y RECOMENDACIÓN", "### 7. CONCLUSIONE E RACCOMANDAZIONE"),
        ("### 8. FUENTES Y NIVEL DE CONFIANZA", "### 8. FONTI E LIVELLO DI AFFIDABILITÀ"),
        ("## REGLAS DE FORMATO", "## REGOLE DI FORMATO"),
        ("[OBSERVACIÓN]", "[OSSERVAZIONE]"),
        ("[INCONSISTENCIA]", "[INCOERENZA]"),
        ("[ALERTA LEVE]", "[ALLERTA LIEVE]"),
        ("[ALERTA MODERADA]", "[ALLERTA MODERATA]"),
        ("[ALERTA CRÍTICA]", "[ALLERTA CRITICA]"),
        ("[INFERENCIA]", "[INFERENZA]"),
        ("No disponible", "Non disponibile"),
        ("Sin evidencia disponible", "Nessuna evidenza disponibile"),
        ("No aplica", "Non applicabile"),
    ],
    "fr": [
        ("DOSSIER EJECUTIVO", "DOSSIER EXÉCUTIF"),
        ("## ESTRUCTURA OBLIGATORIA DEL DOSSIER", "## STRUCTURE OBLIGATOIRE DU DOSSIER"),
        ("### 1. FICHA DE IDENTIDAD", "### 1. FICHE D'IDENTITÉ"),
        ("### 2. RESUMEN EJECUTIVO", "### 2. RÉSUMÉ EXÉCUTIF"),
        ("### 3. TRAYECTORIA PROFESIONAL", "### 3. PARCOURS PROFESSIONNEL"),
        ("### 4. PRESENCIA DIGITAL Y REPUTACIONAL", "### 4. PRÉSENCE NUMÉRIQUE ET RÉPUTATION"),
        ("### 5. ANÁLISIS DE RIESGO", "### 5. ANALYSE DES RISQUES"),
        ("### 6. VÍNCULOS EMPRESARIALES", "### 6. LIENS ENTREPRISE"),
        ("### 7. CONCLUSIÓN Y RECOMENDACIÓN", "### 7. CONCLUSION ET RECOMMANDATION"),
        ("### 8. FUENTES Y NIVEL DE CONFIANZA", "### 8. SOURCES ET NIVEAU DE CONFIANCE"),
        ("## REGLAS DE FORMATO", "## RÈGLES DE FORMAT"),
        ("[OBSERVACIÓN]", "[OBSERVATION]"),
        ("[INCONSISTENCIA]", "[INCOHÉRENCE]"),
        ("[ALERTA LEVE]", "[ALERTE LÉGÈRE]"),
        ("[ALERTA MODERADA]", "[ALERTE MODÉRÉE]"),
        ("[ALERTA CRÍTICA]", "[ALERTE CRITIQUE]"),
        ("[INFERENCIA]", "[INFÉRENCE]"),
        ("No disponible", "Non disponible"),
        ("Sin evidencia disponible", "Aucune preuve disponible"),
        ("No aplica", "Sans objet"),
    ],
    "de": [
        ("DOSSIER EJECUTIVO", "EXECUTIVE-DOSSIER"),
        ("## ESTRUCTURA OBLIGATORIA DEL DOSSIER", "## PFLICHTSTRUKTUR DES DOSSIERS"),
        ("### 1. FICHA DE IDENTIDAD", "### 1. IDENTITÄTSÜBERSICHT"),
        ("### 2. RESUMEN EJECUTIVO", "### 2. ZUSAMMENFASSUNG FÜR DIE GESCHÄFTSLEITUNG"),
        ("### 3. TRAYECTORIA PROFESIONAL", "### 3. BERUFLICHER WERDEGANG"),
        ("### 4. PRESENCIA DIGITAL Y REPUTACIONAL", "### 4. DIGITALE PRÄSENZ UND REPUTATION"),
        ("### 5. ANÁLISIS DE RIESGO", "### 5. RISIKOANALYSE"),
        ("### 6. VÍNCULOS EMPRESARIALES", "### 6. UNTERNEHMENSVERBINDUNGEN"),
        ("### 7. CONCLUSIÓN Y RECOMENDACIÓN", "### 7. FAZIT UND EMPFEHLUNG"),
        ("### 8. FUENTES Y NIVEL DE CONFIANZA", "### 8. QUELLEN UND VERTRAUENSNIVEAU"),
        ("## REGLAS DE FORMATO", "## FORMATREGELN"),
        ("[OBSERVACIÓN]", "[BEOBACHTUNG]"),
        ("[INCONSISTENCIA]", "[INKONSISTENZ]"),
        ("[ALERTA LEVE]", "[LEICHTE WARNUNG]"),
        ("[ALERTA MODERADA]", "[MODERATE WARNUNG]"),
        ("[ALERTA CRÍTICA]", "[KRITISCHE WARNUNG]"),
        ("[INFERENCIA]", "[INFERENZ]"),
        ("No disponible", "Nicht verfügbar"),
        ("Sin evidencia disponible", "Keine Evidenz verfügbar"),
        ("No aplica", "Nicht zutreffend"),
    ],
}


def corporate_dossier_delivery_instructions(code: str | None) -> str:
    lang = normalize_output_language(code)
    return _CORPORATE_DELIVERY.get(lang, _CORPORATE_DELIVERY["es"])


def corporate_dual_scope_note(code: str | None) -> str:
    lang = normalize_output_language(code)
    return _CORPORATE_DUAL_NOTE.get(lang, _CORPORATE_DUAL_NOTE["es"])


def system_writing_line(code: str | None) -> str | None:
    lang = normalize_output_language(code)
    if lang == "es":
        return None
    return _SYSTEM_WRITING_LINE.get(lang)


def localize_person_dossier_prompt(prompt: str, code: str | None) -> str:
    """Compatibilidad: devuelve la plantilla completa del idioma (ignora ``prompt``)."""
    from dossier.services.person_dossier_locales import person_dossier_system_template

    return person_dossier_system_template(code)
