# scripts/scraper/strategies/base.py
#
# Interfaz abstracta para estrategias de extracción de secciones.
# Cada tema de Moodle (Classic, Tiles, etc.) implementa esta interfaz;
# el resto del pipeline trabaja exclusivamente contra ScraperStrategy.

from abc import ABC, abstractmethod

from selenium import webdriver


class ScraperStrategy(ABC):
    """Abstrae la lógica de extracción de secciones para distintos temas de Moodle."""

    @abstractmethod
    def extraer_secciones(
        self,
        browser: webdriver.Chrome,
        curso_url: str,
    ) -> list[dict]:
        """Extrae la estructura de secciones de un curso ya cargado en el browser.

        El browser debe estar posicionado en la URL del curso antes de llamar
        a este método. Las popups ya deben haberse cerrado.

        Returns:
            Lista de dicts con keys:
              - titulo (str)
              - titulo_directorio (str)
              - orden (int)
              - fecha_inicio (str | None)  — ISO 8601
              - fecha_fin    (str | None)  — ISO 8601
              - temas (list[dict])         — cada tema: {nombre, tipo, url}
        """
        ...
