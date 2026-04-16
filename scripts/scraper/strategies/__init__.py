# scripts/scraper/strategies/__init__.py
#
# Factory para instanciar la estrategia de scraping según el tema de Moodle
# configurado en el JSON de la plataforma.

from scripts.scraper.strategies.base import ScraperStrategy
from scripts.scraper.strategies.classic import ClassicScraperStrategy
from scripts.scraper.strategies.tiles import TilesScraperStrategy

_STRATEGIES: dict[str, type[ScraperStrategy]] = {
    "classic": ClassicScraperStrategy,
    "tiles":   TilesScraperStrategy,
}


def get_strategy(theme: str) -> ScraperStrategy:
    """Devuelve la estrategia de scraping para el tema indicado.

    Si el tema no está registrado se usa Classic como fallback con aviso.
    """
    cls = _STRATEGIES.get(theme)
    if cls is None:
        import logging
        logging.getLogger(__name__).warning(
            "tema '%s' no reconocido, usando estrategia classic por defecto.", theme
        )
        cls = ClassicScraperStrategy
    return cls()
