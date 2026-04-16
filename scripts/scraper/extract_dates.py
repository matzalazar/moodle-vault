# scripts/scraper/extract_dates.py
#
# Utilidades para detectar y parsear rangos de fecha en títulos de sección.
# Compartido entre las estrategias Classic y Tiles.

import re
import logging
import datetime

logger = logging.getLogger(__name__)

# ── Formatos soportados ───────────────────────────────────────────────────────

# Classic/UPSO: "01/02/2026 - 07/02/2026" o "2026-02-01 - 2026-02-07"
_PATRON_RANGO_FECHA = re.compile(
    r"(?P<ini>\d{2}/\d{2}/\d{4})\s*-\s*(?P<fin>\d{2}/\d{2}/\d{4})"
)
_PATRON_RANGO_FECHA_ISO = re.compile(
    r"(?P<ini>\d{4}-\d{2}-\d{2})\s*-\s*(?P<fin>\d{4}-\d{2}-\d{2})"
)

# Tiles/FADENA: "Semana 1 - 06/04 al 10/04" (sin año)
_PATRON_RANGO_TILES = re.compile(
    r"(?P<d1>\d{1,2})[/\-](?P<m1>\d{1,2})\s+al\s+(?P<d2>\d{1,2})[/\-](?P<m2>\d{1,2})"
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
    """Extrae fechas inicio/fin de un título de sección.

    Soporta tres formatos:
      - dd/mm/yyyy - dd/mm/yyyy  (Classic/UPSO)
      - yyyy-mm-dd - yyyy-mm-dd  (ISO)
      - dd/mm al dd/mm           (Tiles/FADENA, asume año en curso)
    """
    for patron in (_PATRON_RANGO_FECHA, _PATRON_RANGO_FECHA_ISO):
        m = patron.search(titulo)
        if m:
            return _parse_date(m.group("ini")), _parse_date(m.group("fin"))

    m = _PATRON_RANGO_TILES.search(titulo)
    if m:
        year = datetime.date.today().year
        try:
            f_ini = datetime.date(year, int(m.group("m1")), int(m.group("d1")))
            f_fin = datetime.date(year, int(m.group("m2")), int(m.group("d2")))
            return f_ini, f_fin
        except ValueError:
            logger.warning("invalid date components in tiles title: '%s'", titulo)

    return None, None
