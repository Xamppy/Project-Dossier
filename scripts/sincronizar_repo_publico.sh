#!/usr/bin/env bash
# Sincroniza la copia pública (Xamppy/Project-Dossier-public) desde `main` del repo privado.
#
# Qué hace:
#   1. Clona solo `main` del repo privado en una carpeta temporal (clon desnudo).
#   2. Reescribe el historial con git-filter-repo y quita los archivos con datos personales
#      y la configuración de Dependabot.
#   3. Verifica el historial completo: RUT en texto, PDF y DOCX, y secretos con gitleaks si existe.
#   4. Solo con --push: sube `main` al repo público con push forzado. Sin tags.
#
# Uso:
#   scripts/sincronizar_repo_publico.sh            # prepara y verifica, no sube nada
#   scripts/sincronizar_repo_publico.sh --push     # además sube al público
#
# Requisitos: git, git-filter-repo (`uv tool install git-filter-repo`), Python 3 con PyMuPDF
# para revisar los PDF (`uv pip install pymupdf`), y gitleaks (opcional). Ver docs/dev/repo-publico.md.
set -euo pipefail

PRIVADO="${PRIVADO:-https://github.com/Xamppy/Project-Dossier.git}"
PUBLICO="${PUBLICO:-https://github.com/Xamppy/Project-Dossier-public.git}"
PYTHON="${PYTHON:-python}"

# Archivos que NUNCA deben llegar al público, en ninguna versión del historial.
# Si aparece otro archivo con datos personales, agrégalo aquí (y bórralo de main).
# .github/dependabot.yml también se quita: sin él, Dependabot no abre PR en la copia
# pública. Las dependencias se actualizan en el repo de trabajo.
RUTAS_EXCLUIDAS=(
  "docs/documentos-capstone/1.5_GuiaEstudiante_Fase 1_Definicion Proyecto APT.docx.pdf"
  ".github/dependabot.yml"
)

SUBIR=0
if [[ "${1:-}" == "--push" ]]; then
  SUBIR=1
fi

TRABAJO="$(mktemp -d)"
CLON="$TRABAJO/publico.git"
echo "Carpeta de trabajo: $TRABAJO"

git clone --bare --no-local --single-branch --branch main "$PRIVADO" "$CLON"
# Rutas largas en Windows: sin esto, el repack de filter-repo puede fallar.
git -C "$CLON" config core.longpaths true

ARGS=()
for ruta in "${RUTAS_EXCLUIDAS[@]}"; do
  ARGS+=(--path "$ruta")
done
git -C "$CLON" filter-repo "${ARGS[@]}" --invert-paths --force

echo "== Verificación: RUT en el historial (texto) =="
# RUT aislado; los bordes descartan UUID y números de acceso de la SEC.
RUT_ERE='(^|[^0-9A-Za-z.-])[0-9]{1,2}\.?[0-9]{3}\.?[0-9]{3}-[0-9kK]([^0-9A-Za-z-]|$)'
N_TEXTO="$(git -C "$CLON" log --all -p | grep -acE "$RUT_ERE" || true)"
echo "Líneas con RUT en git log -p: $N_TEXTO"

echo "== Verificación: RUT en PDF y DOCX de todo el historial =="
N_BINARIOS="$("$PYTHON" - "$CLON" <<'PY'
import io, re, subprocess, sys, zipfile
repo = sys.argv[1]
rut = re.compile(r"(?<![\w.-])\d{1,2}\.?\d{3}\.?\d{3}-[\dkK](?![\w-])")
def git(*a, data=None):
    return subprocess.run(["git", "-C", repo, *a], input=data, capture_output=True, check=True).stdout
objs = [l.split(" ", 1) for l in git("rev-list", "--all", "--objects").decode("utf-8", "replace").splitlines()]
total = 0
for sha, *ruta in objs:
    if not ruta or not ruta[0].lower().endswith((".pdf", ".docx")):
        continue
    blob = git("cat-file", "blob", sha)
    if blob[:5] == b"%PDF-":
        import pymupdf
        texto = "\n".join(p.get_text() for p in pymupdf.open(stream=blob, filetype="pdf"))
    else:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            texto = "\n".join(re.sub(r"<[^>]+>", "", z.read(n).decode("utf-8", "ignore"))
                              for n in z.namelist() if n.endswith(".xml"))
    n = len(set(rut.findall(texto)))
    if n:
        print(f"RUT en {ruta[0]} ({sha[:8]}): {n}", file=sys.stderr)
    total += n
print(total)
PY
)"
echo "RUT en PDF/DOCX: $N_BINARIOS"

if [[ "$N_TEXTO" != "0" || "$N_BINARIOS" != "0" ]]; then
  echo "ALTO: quedan RUT en el historial. Agrega el archivo a RUTAS_EXCLUIDAS y vuelve a correr." >&2
  exit 1
fi

if command -v gitleaks >/dev/null 2>&1; then
  echo "== gitleaks =="
  gitleaks detect --source "$CLON" --no-banner --redact \
    || echo "AVISO: gitleaks reportó hallazgos; revísalos antes de subir (hoy hay 5 falsos positivos conocidos)."
else
  echo "AVISO: gitleaks no está instalado; no se revisaron secretos."
fi

if [[ "$SUBIR" == "1" ]]; then
  git -C "$CLON" push --force "$PUBLICO" refs/heads/main:refs/heads/main
  echo "Listo: main sincronizado en $PUBLICO"
else
  echo "Verificación correcta. Para subir: $0 --push"
fi
