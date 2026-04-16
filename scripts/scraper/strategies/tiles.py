# scripts/scraper/strategies/tiles.py
#
# Estrategia para el tema Tiles de Moodle (ej. FADENA - UNDEF).
#
# A diferencia de Classic, el tema Tiles organiza el curso como una cuadrícula
# de "tiles" clickeables (li[id^="tile-"]). Cada tile representa una sección/semana
# y lleva a una URL del tipo ?section=N que contiene las actividades.
#
# Flujo:
#   1. El browser ya cargó la página del curso → extraer cookies y HTML actual.
#   2. Parsear tiles con BeautifulSoup (sin navegación Selenium adicional).
#   3. Para cada tile: GET de la URL de sección con requests + cookies del browser.
#   4. Extraer actividades de cada sección y mapearlas al formato estándar.

import logging
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote

from bs4 import BeautifulSoup
from selenium import webdriver

from scripts.scraper.strategies.base import ScraperStrategy
from scripts.scraper.extract_dates import parsear_rango_semana
from scripts.utils import sanitizar_directorio

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30

# Fragmentos de URL que identifican el tipo de actividad en Moodle
_MOD_TIPO = {
    "/mod/resource/": "Archivo",
    "/mod/folder/":   "Carpeta",
    "/mod/url/":      "URL",
    "/mod/page/":     "Página",
    "/mod/assign/":   "Tarea",
    "/mod/forum/":    "Foro",
    "/mod/quiz/":     "Cuestionario",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tipo_desde_url(url: str) -> str:
    for fragmento, tipo in _MOD_TIPO.items():
        if fragmento in url:
            return tipo
    if "/pluginfile.php" in url or "/draftfile.php" in url:
        return "Archivo"
    return "Recurso"


def _safe_name(value: str) -> str:
    return " ".join(value.split()).strip() or "item"


def _extract_section_number(url: str) -> str | None:
    for chunk in urlparse(url).query.split("&"):
        if chunk.startswith("section="):
            value = chunk.split("=", 1)[1].strip()
            return value or None
    return None


def _is_restricted_tile(tile) -> bool:
    return "tile-restricted" in (tile.get("class") or [])


def _tile_section_links(soup: BeautifulSoup) -> list[dict]:
    """Devuelve los tiles accesibles de la página de portada del curso."""
    tiles = []
    seen: set[str] = set()

    for tile in soup.select('li[id^="tile-"]'):
        if _is_restricted_tile(tile):
            continue

        link = tile.select_one("a.tile-link[href]")
        if link is None:
            continue

        href = link.get("href", "")
        section = _extract_section_number(href)
        if not section or section in seen:
            continue

        seen.add(section)
        title = _safe_name(link.get_text(" ", strip=True))
        tiles.append({
            "section": section,
            "url": href,
            "title": title or f"sección {section}",
        })

    return tiles


def _extraer_temas_de_seccion(
    session: requests.Session,
    section_url: str,
    section_number: str,
    base_host: str,
) -> list[dict]:
    """Recupera una página de sección y extrae sus actividades."""
    try:
        r = session.get(section_url, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logger.error("error al obtener sección %s: %s", section_url, e)
        return []

    soup = BeautifulSoup(r.text, "lxml")

    # Intentar acotarse al contenedor de la sección; si no existe, buscar en toda la página.
    container = (
        soup.select_one(f"li#section-{section_number}")
        or soup.select_one(f"div#section-{section_number}")
        or soup
    )

    temas = []
    seen: set[str] = set()

    for a in container.select("a[href]"):
        href = a.get("href", "")
        if not href or href.startswith(("#", "javascript:")):
            continue

        # Solo actividades del propio dominio Moodle.
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != base_host:
            continue

        # Solo enlaces a módulos o archivos directos.
        is_mod = "/mod/" in href
        is_file = "/pluginfile.php" in href or "/draftfile.php" in href
        if not is_mod and not is_file:
            continue

        if href in seen:
            continue
        seen.add(href)

        text = _safe_name(a.get_text(" ", strip=True))
        nombre = text or Path(unquote(parsed.path)).stem or "recurso"
        tipo = _tipo_desde_url(href)

        temas.append({"nombre": nombre, "tipo": tipo, "url": href})

    return temas


def _build_requests_session(browser: webdriver.Chrome) -> requests.Session:
    """Crea una sesión requests con las cookies actuales del browser."""
    session = requests.Session()
    session.cookies.update({c["name"]: c["value"] for c in browser.get_cookies()})
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session


# ── Estrategia ────────────────────────────────────────────────────────────────

class TilesScraperStrategy(ScraperStrategy):
    """Estrategia para el tema Tiles de Moodle."""

    def extraer_secciones(
        self,
        browser: webdriver.Chrome,
        curso_url: str,
    ) -> list[dict]:
        # Reutilizar el HTML ya cargado por el browser y sus cookies de sesión.
        session = _build_requests_session(browser)
        soup = BeautifulSoup(browser.page_source, "lxml")
        base_host = urlparse(curso_url).netloc

        tiles = _tile_section_links(soup)
        if not tiles:
            logger.warning("no se encontraron tiles en %s", curso_url)
            return []

        logger.info("tiles encontrados: %d", len(tiles))
        secciones = []

        for idx, tile in enumerate(tiles):
            titulo = tile["title"]
            section_url = tile["url"]
            section_number = tile["section"]

            f_ini, f_fin = parsear_rango_semana(titulo)

            prefix = f"{idx + 1:02d}_"
            titulo_dir = prefix + sanitizar_directorio(
                titulo.replace("/", "-"), maxlen=60 - len(prefix)
            )

            logger.info("procesando sección %s: %s", section_number, titulo)
            temas = _extraer_temas_de_seccion(session, section_url, section_number, base_host)

            secciones.append({
                "titulo": titulo,
                "titulo_directorio": titulo_dir,
                "orden": idx + 1,
                "fecha_inicio": f_ini.isoformat() if f_ini else None,
                "fecha_fin":    f_fin.isoformat() if f_fin else None,
                "temas": temas,
            })

        return secciones
