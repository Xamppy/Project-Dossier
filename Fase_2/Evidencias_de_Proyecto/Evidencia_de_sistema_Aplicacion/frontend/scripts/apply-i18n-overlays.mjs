/**
 * Fusiona overlays JSON en archivos locale .ts (actualiza existentes + añade faltantes).
 * Uso: node scripts/apply-i18n-overlays.mjs [pt|de|fr|it|all]
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const messagesDir = path.join(__dirname, "../src/i18n/messages");
const overlaysDir = path.join(__dirname, "i18n-overlays");

function parseTsMessages(text) {
  const entries = new Map();
  const order = [];
  const re =
    /^\s+"([^"]+)":\s*(?:\n\s*)?(?:"((?:\\.|[^"\\])*)"|`((?:\\.|[^`\\])*)`)\s*,?\s*$/gm;
  let m;
  while ((m = re.exec(text)) !== null) {
    const key = m[1];
    const val = (m[2] ?? m[3] ?? "").replace(/\\"/g, '"').replace(/\\n/g, "\n");
    if (!entries.has(key)) order.push(key);
    entries.set(key, val);
  }
  return { entries, order };
}

function escapeTsString(s) {
  return s
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\r/g, "\\r")
    .replace(/\n/g, "\\n")
    .replace(/\t/g, "\\t");
}

function formatEntry(key, value) {
  const esc = escapeTsString(value);
  if (value.length > 72 && !value.includes("\n")) {
    return `  "${key}":\n    "${esc}",`;
  }
  return `  "${key}": "${esc}",`;
}

function applyOverlay(locale) {
  const overlayPath = path.join(overlaysDir, `${locale}.json`);
  if (!fs.existsSync(overlayPath)) {
    console.error(`No overlay: ${overlayPath}`);
    return false;
  }
  const overlay = JSON.parse(fs.readFileSync(overlayPath, "utf8"));
  const tsPath = path.join(messagesDir, `${locale}.ts`);
  const raw = fs.readFileSync(tsPath, "utf8");
  const { entries, order } = parseTsMessages(raw);

  for (const [k, v] of Object.entries(overlay)) {
    if (!entries.has(k)) order.push(k);
    entries.set(k, v);
  }

  const lines = ["const messages = {"];
  for (const key of order) {
    lines.push(formatEntry(key, entries.get(key)));
  }
  lines.push("} as const;", "", "export default messages;", "");
  fs.writeFileSync(tsPath, lines.join("\n"), "utf8");
  console.log(`${locale}: ${Object.keys(overlay).length} claves aplicadas → ${order.length} total`);
  return true;
}

const arg = process.argv[2] ?? "all";
const locales = arg === "all" ? ["pt", "de", "fr", "it"] : [arg];
let ok = true;
for (const loc of locales) {
  if (!applyOverlay(loc)) ok = false;
}
process.exit(ok ? 0 : 1);
