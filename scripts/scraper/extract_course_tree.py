# scripts/scraper/extract_course_tree.py
#
# Segunda etapa del pipeline: navega a cada curso, extrae su estructura
# jerárquica (secciones → temas) y la persiste en JSON.
#
# El árbol se genera incrementalmente: en cada corrida se mergea con la
# versión anterior para preservar el estado "revisado" de los temas ya
# procesados por download_files.

import re
import json
import time
import logging
import datetime
import argparse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from scripts.platform import load_platform, PlatformConfig
from scripts.scraper.session import get_authenticated_browser
from scripts.scraper.fetch_links import cerrar_popups, ir_a_mis_cursos
from scripts.scraper.selectors import (
    SECTION,
    SECTION_TITLE_A,
    SECTION_TITLE,
    ACTIVITY,
    ACTIVITY_LINK,
    EXPAND_BTN,
    COLLAPSED_ITEMS,
)
from scripts.utils import sanitizar_directorio, setup_logging

logger = logging.getLogger(__name__)

# Patrones de rango de fecha reconocidos en títulos de sección.
# Se prueban en orden; el primero en hacer match gana.
PATRON_RANGO_FECHA = re.compile(
    r"(?P<ini>\d{2}/\d{2}/\d{4})\s*-\s*(?P<fin>\d{2}/\d{2}/\d{4})"
)
PATRON_RANGO_FECHA_ISO = re.compile(
    r"(?P<ini>\d{4}-\d{2}-\d{2})\s*-\s*(?P<fin>\d{4}-\d{2}-\d{2})"
)

_DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]


def _parse_date(s: str) -> datetime.date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    logger.warning("could not parse date: '%s'", s)
    return None


def parsear_rango_semana(
    titulo: str,
) -> tuple[datetime.date | None, datetime.date | None]:
    """Extrae las fechas de inicio y fin del título de una sección."""
    for patron in (PATRON_RANGO_FECHA, PATRON_RANGO_FECHA_ISO):
        m = patron.search(titulo)
        if m:
            return _parse_date(m.group("ini")), _parse_date(m.group("fin"))
    return None, None


def expandir_todo(browser: webdriver.Chrome) -> None:
    try:
        btn = browser.find_element(By.CSS_SELECTOR, EXPAND_BTN)
        if btn.is_displayed():
            btn.click()
            time.sleep(2)
            return
    except NoSuchElementException:
        pass

    # Algunas versiones de Moodle no tienen el botón "expandir todo";
    # en ese caso se eliminan las clases CSS de colapso directamente.
    try:
        browser.execute_script(
            f"document.querySelectorAll('{COLLAPSED_ITEMS}').forEach(el => el.classList.remove('collapsed'));"
        )
        time.sleep(1)
    except Exception:
        pass


def extraer_secciones(browser: webdriver.Chrome) -> list[dict]:
    """Extrae secciones en orden DOM, sin reordenar."""
    secciones = []
    bloques = browser.find_elements(By.CSS_SELECTOR, SECTION)

    for idx, bloque in enumerate(bloques):
        try:
            titulo_elem = bloque.find_element(By.CSS_SELECTOR, SECTION_TITLE_A)
            titulo = titulo_elem.text.strip()
        except NoSuchElementException:
            try:
                titulo = bloque.find_element(By.CSS_SELECTOR, SECTION_TITLE).text.strip()
            except NoSuchElementException:
                titulo = "(sin titulo)"

        f_ini, f_fin = parsear_rango_semana(titulo)

        # El prefijo numérico garantiza orden alfabético correcto en el filesystem.
        prefix = f"{idx + 1:02d}_"
        titulo_sanitizado = sanitizar_directorio(titulo.replace("/", "-"), maxlen=60 - len(prefix))
        titulo_directorio = prefix + titulo_sanitizado

        temas = []
        actividades = bloque.find_elements(By.CSS_SELECTOR, ACTIVITY)
        for actividad in actividades:
            try:
                enlace = actividad.find_element(By.CSS_SELECTOR, ACTIVITY_LINK)
                nombre_completo = enlace.text.strip()
                url = enlace.get_attribute("href")

                # Moodle incluye el tipo de actividad como segunda línea del texto
                # del enlace (ej. "Apuntes\nArchivo"). Se separa si está presente.
                if "\n" in nombre_completo:
                    nombre, tipo = nombre_completo.split("\n", 1)
                else:
                    nombre, tipo = nombre_completo, ""

                temas.append({
                    "nombre": nombre.strip(),
                    "tipo": tipo.strip(),
                    "url": url
                })
            except NoSuchElementException:
                continue

        secciones.append({
            "titulo": titulo,
            "titulo_directorio": titulo_directorio,
            "orden": idx + 1,
            "fecha_inicio": f_ini.isoformat() if f_ini else None,
            "fecha_fin":    f_fin.isoformat() if f_fin else None,
            "temas": temas
        })

    return secciones


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
            "temas": temas_mergeados
        })
    return merged


def procesar_curso(
    browser: webdriver.Chrome,
    curso: dict,
    tree_dir: Path,
) -> None:
    logger.info("processing course: %s", curso["nombre"])
    browser.get(curso["url"])
    time.sleep(3)
    cerrar_popups(browser)
    expandir_todo(browser)
    nuevas_secciones = extraer_secciones(browser)

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
        "semanas": secciones_actualizadas
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

    for curso in cursos_seguimiento:
        procesar_curso(browser, curso, platform.tree_dir)
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
