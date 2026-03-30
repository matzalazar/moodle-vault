# scripts/utils.py
#
# Utilidades compartidas por todo el pipeline: sanitización de nombres,
# registro de descargas y constantes de configuración.

import os
import re
import sys
import fcntl
import unicodedata
import logging
from pathlib import Path
from datetime import datetime

# Respetar el estándar NO_COLOR (https://no-color.org/): cualquier valor no
# vacío en la variable deshabilita los códigos de escape ANSI. También se
# deshabilitan cuando la salida no es una terminal (ej. redirección a archivo).
_USE_COLOR = not os.environ.get("NO_COLOR") and sys.stderr.isatty()

_R  = "\033[0m"  if _USE_COLOR else ""
_C  = "\033[36m" if _USE_COLOR else ""   # cyan  → info
_Y  = "\033[33m" if _USE_COLOR else ""   # yellow → warning
_RE = "\033[31m" if _USE_COLOR else ""   # red   → error
_DI = "\033[2m"  if _USE_COLOR else ""   # dim   → debug

_PREFIJOS = {
    logging.DEBUG:    f"{_DI}[·]{_R}",
    logging.INFO:     f"{_C}[+]{_R}",
    logging.WARNING:  f"{_Y}[!]{_R}",
    logging.ERROR:    f"{_RE}[x]{_R}",
    logging.CRITICAL: f"{_RE}[x]{_R}",
}


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        prefix = _PREFIJOS.get(record.levelno, "·")
        msg = record.getMessage()
        return f"{prefix} {msg}"


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_ColorFormatter())
    root.setLevel(logging.INFO)
    root.addHandler(handler)


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# Extensiones que el scraper considera descargables. Cualquier link cuyo path
# termine con una de estas (case-insensitive) se trata como archivo a bajar.
EXTENSIONES_CONOCIDAS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".zip", ".rar", ".7z", ".ipynb", ".py", ".txt", ".csv",
    ".mp4", ".mp3",
}

logger = logging.getLogger(__name__)


def sanitizar_directorio(nombre: str, maxlen: int = 60) -> str:
    # NFD descompone los caracteres con diacríticos en base + marca de acento,
    # lo que permite eliminar solo las marcas (categoría "Mn") sin tocar la base.
    nombre = unicodedata.normalize("NFD", nombre)
    nombre = "".join(c for c in nombre if unicodedata.category(c) != "Mn")
    nombre = re.sub(r"[^a-zA-Z0-9-]+", "_", nombre.strip())
    nombre = re.sub(r"_+", "_", nombre)
    resultado = nombre.strip("_")
    if len(resultado) > maxlen:
        logger.debug(
            "nombre truncado de %d a %d caracteres: '%s'",
            len(resultado), maxlen, resultado[:maxlen],
        )
        return resultado[:maxlen]
    return resultado


def sanitizar_nombre_archivo(nombre: str, maxlen: int = 100) -> str:
    """Sanitiza preservando la extensión cuando es reconocida."""
    p = Path(nombre)
    ext = p.suffix.lower()
    if ext in EXTENSIONES_CONOCIDAS:
        # Limitar el stem para que stem + extensión no supere maxlen total.
        stem = sanitizar_directorio(p.stem, maxlen - len(ext))
        resultado = stem + ext
        if len(nombre) > maxlen:
            logger.debug("filename truncated: '%s' -> '%s'", nombre, resultado)
        return resultado
    return sanitizar_directorio(nombre, maxlen)


def registrar_descarga_log(
    nombre_archivo: str,
    curso: str,
    semana: str,
    tema: str,
    platform_name: str,
) -> None:
    # El log "actual" se renueva en cada ejecución de main.sh;
    # al terminar el pipeline, ese archivo se renombra con timestamp.
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    current_log = LOG_DIR / f"{platform_name}_descargas_actual.log"
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{fecha}] {curso} | {semana} > {tema} => {nombre_archivo}\n"
    with open(current_log, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(linea)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
