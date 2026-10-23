import fs from "fs";
import path from "path";

import { fileURLToPath } from "url";
const scriptsDir = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(scriptsDir, "../src/i18n/messages");

function parseMessages(file) {
  const text = fs.readFileSync(path.join(dir, file), "utf8");
  const re = /^\s+"([^"]+)":\s*(?:"((?:\\.|[^"\\])*)"|`((?:\\.|[^`\\])*)`|\n\s*"((?:\\.|[^"\\])*)")/gm;
  const out = {};
  let m;
  while ((m = re.exec(text)) !== null) {
    out[m[1]] = m[2] ?? m[3] ?? m[4] ?? "";
  }
  return out;
}

const en = parseMessages("en.ts");
const es = parseMessages("es.ts");

for (const loc of ["pt", "de", "fr", "it"]) {
  const locMsgs = parseMessages(`${loc}.ts`);
  const missing = {};
  for (const [k, v] of Object.entries(en)) {
    if (!(k in locMsgs)) missing[k] = { en: v, es: es[k] ?? null };
  }
  fs.writeFileSync(
    path.join(scriptsDir, `i18n-missing-${loc}.json`),
    JSON.stringify(missing, null, 2),
    "utf8",
  );
  console.log(`${loc}: ${Object.keys(missing).length} missing`);
}
