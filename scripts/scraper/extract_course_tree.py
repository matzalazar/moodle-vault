# scripts/scraper/extract_course_tree.py
#
# Segunda etapa del pipeline: navega a cada curso, extrae su estructura
# jerárquica (secciones → temas) y la persiste en JSON.
#
# La lógica de extracción está delegada a una ScraperStrategy que se
# selecciona según el campo "theme" del JSON de la plataforma.
# Actualmente se soportan:
#   - "classic" → tema Boost/Classic de Moodle (UPSO)
#   - "tiles"   → tema Tiles de Moodle (FADENA)
#
# El árbol se genera incrementalmente: en cada corrida se mergea con la
# versión anterior para preservar el estado "revisado" de los temas ya
# procesados por download_files.

import json
import time
import logging
import argparse
from pathlib import Path

from selenium import webdriver

from scripts.platform import load_platform, PlatformConfig
from scripts.scraper.session import get_authenticated_browser
from scripts.scraper.fetch_links import cerrar_popups
from scripts.scraper.strategies import get_strategy
from scripts.scraper.strategies.base import ScraperStrategy
from scripts.utils import sanitizar_directorio, setup_logging

logger = logging.getLogger(__name__)


def merge_secciones(nuevas: list[dict], anteriores: list[dict]) -> list[dict]:
    """Combina la estructura recién extraída con la del run anterior.

    Solo se propaga el estado 'revisado: true'; los temas cuya URL cambió
    (recurso reemplazado por el docente) se tratan como nuevos.
    """
    merged = []
    for nueva in nuevas:
        titulo = nueva["titulo"]
        temas_nuevos = nueva["temas"]

        temas_anteriores: list[dict] = []
        for vieja in anteriores:
            if vieja.get("titulo") == titulo:
                temas_anteriores = vieja.get("temas", [])
                break

        temas_mergeados = []
        for nt in temas_nuevos:
            ya = next((t for t in temas_anteriores if t.get("url") == nt.get("url")), None)
            if ya and ya.get("revisado") is True:
                nt["revisado"] = True
            temas_mergeados.append(nt)

        merged.append({
            "titulo": titulo,
            "titulo_directorio": nueva.get("titulo_directorio"),
            "orden": nueva.get("orden"),
            "fecha_inicio": nueva.get("fecha_inicio"),
            "fecha_fin": nueva.get("fecha_fin"),
            "temas": temas_mergeados,
        })
    return merged


def procesar_curso(
    browser: webdriver.Chrome,
    curso: dict,
    tree_dir: Path,
    strategy: ScraperStrategy,
) -> None:
    logger.info("processing course: %s", curso["nombre"])
    browser.get(curso["url"])
    time.sleep(3)
    cerrar_popups(browser)

    nuevas_secciones = strategy.extraer_secciones(browser, curso["url"])

    filename = tree_dir / f"{sanitizar_directorio(curso['nombre'].replace('/', '-'))}.json"
    if filename.exists():
        with open(filename, "r", encoding="utf-8") as f:
            anterior = json.load(f)
            anteriores_secciones = anterior.get("semanas", [])
    else:
        anteriores_secciones = []

    secciones_actualizadas = merge_secciones(nuevas_secciones, anteriores_secciones)

    estructura = {
        "curso": curso["nombre"],
        "semanas": secciones_actualizadas,
    }

    tree_dir.mkdir(parents=True, exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(estructura, f, indent=2, ensure_ascii=False)

    logger.info("tree saved to %s", filename)


def run(browser: webdriver.Chrome, platform: PlatformConfig) -> None:
    """Extrae árbol de cursos usando el browser provisto. No crea ni cierra el browser."""
    if not platform.course_links_path.exists():
        logger.error("%s not found. create it with a list of courses:", platform.course_links_path)
        logger.error('[{"nombre": "Nombre Curso", "url": "https://...", "seguimiento": true}]')
        return

    with open(platform.course_links_path, "r", encoding="utf-8") as f:
        cursos = json.load(f)

    cursos_seguimiento = [c for c in cursos if c.get("seguimiento", False)]
    if not cursos_seguimiento:
        logger.warning("no courses marked for tracking.")
        return

    strategy = get_strategy(platform.theme)
    logger.info("using scraper strategy: %s (theme: %s)", type(strategy).__name__, platform.theme)

    for curso in cursos_seguimiento:
        procesar_curso(browser, curso, platform.tree_dir, strategy)

    logger.info("done.")


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, help="nombre de la plataforma")
    args = parser.parse_args()

    platform = load_platform(args.platform)

    browser = get_authenticated_browser(platform)
    try:
        run(browser, platform)
    finally:
        browser.quit()


if __name__ == "__main__":
    main()
