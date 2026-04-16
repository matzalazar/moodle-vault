# scripts/scraper/strategies/classic.py
#
# Estrategia para el tema Classic/Boost de Moodle (ej. UPSO).
# Usa Selenium directamente: expande secciones colapsadas y recorre
# la estructura li.section.main > li.activity para extraer temas.

import time
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from scripts.scraper.strategies.base import ScraperStrategy
from scripts.scraper.selectors import (
    SECTION,
    SECTION_TITLE_A,
    SECTION_TITLE,
    ACTIVITY,
    ACTIVITY_LINK,
    EXPAND_BTN,
    COLLAPSED_ITEMS,
)
from scripts.scraper.extract_dates import parsear_rango_semana
from scripts.utils import sanitizar_directorio

logger = logging.getLogger(__name__)


def _expandir_todo(browser: webdriver.Chrome) -> None:
    try:
        btn = browser.find_element(By.CSS_SELECTOR, EXPAND_BTN)
        if btn.is_displayed():
            btn.click()
            time.sleep(2)
            return
    except NoSuchElementException:
        pass

    # Si no hay botón, eliminar clases de colapso directamente vía JS.
    try:
        browser.execute_script(
            f"document.querySelectorAll('{COLLAPSED_ITEMS}').forEach(el => el.classList.remove('collapsed'));"
        )
        time.sleep(1)
    except Exception:
        pass


class ClassicScraperStrategy(ScraperStrategy):
    """Estrategia para el tema Classic/Boost de Moodle."""

    def extraer_secciones(
        self,
        browser: webdriver.Chrome,
        curso_url: str,
    ) -> list[dict]:
        _expandir_todo(browser)

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

            prefix = f"{idx + 1:02d}_"
            titulo_sanitizado = sanitizar_directorio(
                titulo.replace("/", "-"), maxlen=60 - len(prefix)
            )
            titulo_directorio = prefix + titulo_sanitizado

            temas = []
            for actividad in bloque.find_elements(By.CSS_SELECTOR, ACTIVITY):
                try:
                    enlace = actividad.find_element(By.CSS_SELECTOR, ACTIVITY_LINK)
                    nombre_completo = enlace.text.strip()
                    url = enlace.get_attribute("href")

                    # Moodle incluye el tipo de actividad como segunda línea del texto.
                    if "\n" in nombre_completo:
                        nombre, tipo = nombre_completo.split("\n", 1)
                    else:
                        nombre, tipo = nombre_completo, ""

                    temas.append({
                        "nombre": nombre.strip(),
                        "tipo": tipo.strip(),
                        "url": url,
                    })
                except NoSuchElementException:
                    continue

            secciones.append({
                "titulo": titulo,
                "titulo_directorio": titulo_directorio,
                "orden": idx + 1,
                "fecha_inicio": f_ini.isoformat() if f_ini else None,
                "fecha_fin":    f_fin.isoformat() if f_fin else None,
                "temas": temas,
            })

        return secciones
