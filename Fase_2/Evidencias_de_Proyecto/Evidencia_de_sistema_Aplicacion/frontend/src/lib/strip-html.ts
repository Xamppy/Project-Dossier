/** Quita etiquetas HTML y deja una línea legible (títulos de dossier / calendario). */
export function stripHtmlToPlainLine(raw: string | null | undefined, maxLen?: number): string {
  if (!raw?.trim()) return "";
  let t = raw
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|tr|h[1-6]|pre)>/gi, "\n")
    .replace(/<[^>]+>/g, " ");
  t = t
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
  const line = t.replace(/\s+/g, " ").trim();
  if (maxLen != null && maxLen > 0) {
    return line.slice(0, maxLen);
  }
  return line;
}
