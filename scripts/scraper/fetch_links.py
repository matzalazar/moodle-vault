# scripts/scraper/fetch_links.py
#
# Primera etapa del pipeline: navega a "Mis cursos" y extrae las URLs
# de cada curso disponible. En la primera ejecución pregunta interactivamente
# cuáles seguir; las ejecuciones posteriores usan el archivo guardado.

import sys
import time
import json
import logging
import argparse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    NoSuchElementException,
    ElementNotInteractableException,
)

from scripts.platform import load_platform, PlatformConfig
from scripts.scraper.session import get_authenticated_browser
from scripts.utils import setup_logging
from scripts.scraper.selectors import (
    MIS_CURSOS_CANDIDATOS,
    COURSE_LINK,
    POPUP_CLOSE_SELECTORS,
    POPUP_OVERLAY_JS,
)

logger = logging.getLogger(__name__)

# Máximo de intentos para la pregunta interactiva de seguimiento.
# Si el usuario ingresa respuestas inválidas repetidamente se asume "n"
# para no bloquear el pipeline indefinidamente.
_MAX_INTENTOS_SEGUIMIENTO = 3


def ya_configurado(filepath: Path) -> bool:
    """Devuelve True si todos los cursos en el archivo ya tienen el campo 'seguimiento'."""
    if not filepath.exists():
        return False
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        return all("seguimiento" in curso for curso in data)


def cerrar_popups(browser: webdriver.Chrome) -> None:
    """Cierra overlays o popups que puedan bloquear la interacción."""
    for selector in POPUP_CLOSE_SELECTORS:
        try:
            btn = browser.find_element(By.CSS_SELECTOR, selector)
            if btn.is_displayed():
                btn.click()
                time.sleep(1)
                return
        except (NoSuchElementException, ElementNotInteractableException):
            continue

    # Si ningún botón de cierre fue encontrado, ocultar los overlays directamente
    # vía JS. Es menos limpio que un click, pero efectivo para bloqueos residuales.
    browser.execute_script(
        f"document.querySelectorAll('{POPUP_OVERLAY_JS}').forEach(el => el.style.display = 'none');"
    )
    time.sleep(0.5)


def ir_a_mis_cursos(browser: webdriver.Chrome, timeout: int = 10) -> None:
    cerrar_popups(browser)

    # Se prueban varios selectores porque el enlace varía según la versión
    # de Moodle y el tema visual instalado en cada institución.
    for how, what in MIS_CURSOS_CANDIDATOS:
        try:
            el = WebDriverWait(browser, timeout).until(EC.element_to_be_clickable((how, what)))
            try:
                el.click()
            except ElementClickInterceptedException:
                # Algún overlay interceptó el click; se cierra y se reintenta vía JS.
                cerrar_popups(browser)
                browser.execute_script("arguments[0].click();", el)
            time.sleep(2)
            return
        except TimeoutException:
            continue

    raise RuntimeError("no se pudo acceder a 'mis cursos'. verificá la URL de login y los selectores.")


def preguntar_seguimiento(nombre: str) -> bool:
    for intento in range(1, _MAX_INTENTOS_SEGUIMIENTO + 1):
        resp = input(f"seguimiento para \"{nombre}\"? (y/n): ").strip().lower()
        if resp in ("y", "n"):
            return resp == "y"
        print(f"  respuesta inválida ({intento}/{_MAX_INTENTOS_SEGUIMIENTO}). ingresá 'y' o 'n'.")
    logger.warning(
        "no se obtuvo respuesta válida para '%s' después de %d intentos. asumiendo 'n'.",
        nombre, _MAX_INTENTOS_SEGUIMIENTO,
    )
    return False


def extraer_links_de_cursos(browser: webdriver.Chrome) -> list[dict]:
    cursos = []
    time.sleep(2)
    enlaces = browser.find_elements(By.CSS_SELECTOR, COURSE_LINK)

    for enlace in enlaces:
        # El texto del enlace a veces incluye el prefijo "Nombre del curso\n"
        # generado por Moodle como texto accesible; se elimina si está presente.
        nombre = enlace.text.strip().replace("Nombre del curso\n", "", 1)
        url = enlace.get_attribute("href")

        if not nombre:
            logger.warning("course link has no name, skipping: %s", url)
            continue
        if not url:
            logger.warning("course link has no URL, skipping: %s", nombre)
            continue

        seguimiento = preguntar_seguimiento(nombre)
        cursos.append({
            "nombre": nombre,
            "url": url,
            "seguimiento": seguimiento
        })

    return cursos


def guardar_links(cursos: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cursos, f, indent=2, ensure_ascii=False)
    logger.info("course links saved to %s", output_path)


def run(browser: webdriver.Chrome, platform: PlatformConfig) -> None:
    """Extrae links de cursos usando el browser provisto. No crea ni cierra el browser."""
    if ya_configurado(platform.course_links_path):
        logger.info("%s ya configurado. usando existente.", platform.course_links_path)
        return
    try:
        ir_a_mis_cursos(browser)
    except RuntimeError as e:
        logger.error("%s", e)
        raise
    cursos = extraer_links_de_cursos(browser)
    guardar_links(cursos, platform.course_links_path)


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, help="nombre de la plataforma")
    args = parser.parse_args()

    platform = load_platform(args.platform)

    if ya_configurado(platform.course_links_path):
        logger.info("%s ya configurado. usando existente.", platform.course_links_path)
        return

    browser = get_authenticated_browser(platform)
    try:
        run(browser, platform)
    except Exception:
        sys.exit(1)
    finally:
        browser.quit()


if __name__ == "__main__":
    main()
