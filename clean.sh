#!/bin/bash
#
# Elimina todo el contenido generado por el pipeline: árboles de cursos,
# archivos descargados, selección de cursos y logs de sesión.
#
# Uso: bash clean.sh [-n]
#   -n  dry-run: muestra qué se eliminaría sin borrar nada.

DRY_RUN=0

while getopts "n" opt; do
    case $opt in
        n) DRY_RUN=1 ;;
        *) echo "uso: $0 [-n]"; exit 1 ;;
    esac
done

echo "[!] esto eliminará todo el contenido generado:"
echo "   data/*/trees/               (árboles de cursos)"
echo "   data/*/course/              (archivos descargados)"
echo "   config/*/course_links.json  (selección de cursos)"
echo "   logs/                       (registros de descarga)"
echo ""

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[~] modo dry-run: los siguientes archivos/directorios serían eliminados:"
    find data/*/course data/*/trees -mindepth 1 -maxdepth 1 -type f 2>/dev/null
    find data/*/course data/*/trees -mindepth 1 -maxdepth 1 -type d 2>/dev/null
    find logs -mindepth 1 -maxdepth 1 -not -name ".gitkeep" -type f 2>/dev/null
    find logs -mindepth 1 -maxdepth 1 -not -name ".gitkeep" -type d 2>/dev/null
    find config -name "course_links.json" -type f 2>/dev/null
    exit 0
fi

read -p "confirmar? (y/n): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "[-] cancelado."
    exit 0
fi

find data/*/course data/*/trees -mindepth 1 -maxdepth 1 -type f -exec rm -f {} + 2>/dev/null
find data/*/course data/*/trees -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} + 2>/dev/null
find logs -mindepth 1 -maxdepth 1 -not -name ".gitkeep" -type f -exec rm -f {} + 2>/dev/null
find logs -mindepth 1 -maxdepth 1 -not -name ".gitkeep" -type d -exec rm -rf {} + 2>/dev/null
find config -name "course_links.json" -type f -delete

echo "[+] limpieza completada."
