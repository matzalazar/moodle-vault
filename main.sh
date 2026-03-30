#!/bin/bash
#
# Orquestador principal del pipeline de scraping.
#
# Etapas:
#   1. fetch_links          — extrae las URLs de los cursos disponibles
#   2. extract_course_tree  — construye el árbol jerárquico de cada curso
#   3. reset_semanas        — (opcional) limpia revisado en semanas recientes
#   4. download_files       — descarga los archivos de cada tema
#
# Las integraciones con Todoist y Notion se activan por plataforma desde .env
# con las variables {PLATAFORMA}_TODOIST_ENABLED y {PLATAFORMA}_NOTION_ENABLED.

if [ ! -f ".env" ]; then
    echo "[x] no se encontró .env. copiá .env.example y completá tus credenciales:"
    echo "   cp .env.example .env"
    exit 1
fi

set -a; source .env; set +a

mkdir -p config/platforms
mkdir -p logs

# Log temporal hasta conocer la plataforma; se renombra más abajo.
_TMP_LOG="logs/.run-tmp-$(date +"%Y-%m-%d-%H-%M-%S").log"
exec > >(tee >( sed 's/\x1B\[[0-9;]*[mK]//g' >> "$_TMP_LOG" )) 2>&1

# ── Selección de plataforma ───────────────────────────────────────────────────

mapfile -t PLATFORMS < <(ls config/platforms/*.json 2>/dev/null | xargs -I{} basename {} .json)

if [ ${#PLATFORMS[@]} -eq 0 ]; then
    echo "[x] no se encontraron plataformas en config/platforms/. creá al menos un archivo .json."
    exit 1
fi

if [ ${#PLATFORMS[@]} -eq 1 ]; then
    PLATFORM="${PLATFORMS[0]}"
    echo "[+] plataforma detectada: $PLATFORM"
    LOG_FILE="logs/run-${PLATFORM}-$(date +"%Y-%m-%d-%H-%M-%S").log"
    mv "$_TMP_LOG" "$LOG_FILE"
else
    echo "[-] plataformas disponibles:"
    for i in "${!PLATFORMS[@]}"; do
        echo "  [$((i+1))] ${PLATFORMS[$i]}"
    done
    read -p "seleccioná una plataforma (número): " PLATFORM_IDX
    if ! [[ "$PLATFORM_IDX" =~ ^[0-9]+$ ]] || \
       [ "$PLATFORM_IDX" -lt 1 ] || \
       [ "$PLATFORM_IDX" -gt "${#PLATFORMS[@]}" ]; then
        echo "[x] selección inválida: '$PLATFORM_IDX'. ingresá un número entre 1 y ${#PLATFORMS[@]}."
        exit 1
    fi
    PLATFORM="${PLATFORMS[$((PLATFORM_IDX-1))]}"
    echo "[+] platform selected: $PLATFORM"
    LOG_FILE="logs/run-${PLATFORM}-$(date +"%Y-%m-%d-%H-%M-%S").log"
    mv "$_TMP_LOG" "$LOG_FILE"
fi

# ── Re-scraping de semanas anteriores ────────────────────────────────────────
# Útil cuando el docente sube contenido con retraso y las semanas ya fueron
# procesadas. Resetea el flag "revisado" para que download_files las vuelva
# a procesar en esta ejecución.

echo ""
echo "[-] ¿re-scrapear semanas con contenido subido tarde?"
echo "  [0] no  (por defecto)"
echo "  [1] última semana"
echo "  [2] últimas dos semanas"
read -p "opción: " RESCRAPE_OPT

case "$RESCRAPE_OPT" in
    1) RESCRAPE=1 ;;
    2) RESCRAPE=2 ;;
    *) RESCRAPE=0 ;;
esac

# ── Preparar directorios ──────────────────────────────────────────────────────

mkdir -p "config/$PLATFORM"
mkdir -p "data/$PLATFORM/trees"
mkdir -p "data/$PLATFORM/course"

rm -f "logs/${PLATFORM}_descargas_actual.log"

# ── Pipeline ──────────────────────────────────────────────────────────────────

echo ""
echo "[-] ejecutando scraping ($PLATFORM)..."
python3 -m scripts.scraper.pipeline --platform "$PLATFORM" --rescrape "$RESCRAPE" || exit 1

# ── Integraciones ─────────────────────────────────────────────────────────────
# Se leen las variables {PLATAFORMA}_TODOIST_ENABLED y {PLATAFORMA}_NOTION_ENABLED
# del .env. Solo se ejecutan si el valor es exactamente "true".

PLATFORM_UPPER=$(echo "$PLATFORM" | tr '[:lower:]' '[:upper:]')

# Leer las variables de habilitación usando expansión indirecta de bash
# (evita el uso de eval, que podría ejecutar código arbitrario si PLATFORM
# contuviera caracteres especiales).
_todoist_var="${PLATFORM_UPPER}_TODOIST_ENABLED"
TODOIST_ENABLED="${!_todoist_var}"
_notion_var="${PLATFORM_UPPER}_NOTION_ENABLED"
NOTION_ENABLED="${!_notion_var}"

ACTUAL_LOG="logs/${PLATFORM}_descargas_actual.log"
if [ -f "$ACTUAL_LOG" ]; then
    timestamp=$(date +"%Y%m%d-%H%M%S")
    final_log="logs/${PLATFORM}_descargas_${timestamp}.log"
    mv "$ACTUAL_LOG" "$final_log"
    echo "[+] log de descargas: $final_log"

    if [ -n "$TODOIST_TOKEN" ] && [ "$TODOIST_ENABLED" = "true" ]; then
        echo "[-] enviando tareas a todoist..."
        if ! python3 -m scripts.integrations.todoist --platform "$PLATFORM"; then
            echo "[!] integración todoist falló; se continúa sin interrumpir el pipeline."
        fi
    fi

    if [ -n "$NOTION_TOKEN" ] && [ -n "$NOTION_DATABASE_ID" ] && [ "$NOTION_ENABLED" = "true" ]; then
        echo "[-] enviando entradas a notion..."
        if ! python3 -m scripts.integrations.notion --platform "$PLATFORM"; then
            echo "[!] integración notion falló; se continúa sin interrumpir el pipeline."
        fi
    fi
else
    echo "[-] no se encontraron descargas nuevas en esta ejecución."
fi

echo "[+] finalizado."
