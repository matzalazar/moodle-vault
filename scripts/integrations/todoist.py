# scripts/integrations/todoist.py
#
# Lee el log de descargas más reciente y crea una tarea en Todoist por cada
# archivo descargado, con vencimiento para hoy y prioridad media.
#
# Requiere TODOIST_TOKEN configurado en .env.

import os
import re
import sys
import logging
import argparse
import requests
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from dotenv import load_dotenv

from scripts.utils import setup_logging

load_dotenv()

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

logger = logging.getLogger(__name__)

# Mismo formato que notion.py — ambos leen el mismo archivo de log.
PATRON = re.compile(
    r"\[(?P<fecha>[^\]]+)\]\s+(?P<curso>.+?)\s+\|\s+(?P<semana>.+?)\s+>\s+(?P<tema>.+?)\s+=>\s+(?P<archivo>.+)"
)

# Límite de caracteres del campo "content" de la API REST v2 de Todoist.
_MAX_CONTENT = 500
_REQUEST_TIMEOUT = (5, 20)
_RETRY_STATUS = (429, 500, 502, 503, 504)


def _build_http_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=_RETRY_STATUS,
        allowed_methods=frozenset(["POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def crear_tarea_todoist(
    nombre_archivo: str,
    curso: str,
    semana: str,
    tema: str,
    token: str,
    http_session: requests.Session,
) -> None:
    url = "https://api.todoist.com/rest/v2/tasks"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    contenido = f"nueva descarga en moodle: {nombre_archivo}\ncurso: {curso}\nsemana: {semana}\ntema: {tema}"
    if len(contenido) > _MAX_CONTENT:
        logger.warning(
            "contenido de tarea truncado (%d -> %d caracteres)",
            len(contenido), _MAX_CONTENT,
        )
        contenido = contenido[:_MAX_CONTENT - 3] + "..."

    data = {
        "content": contenido,
        "due_string": "today",
        "priority": 3,
    }

    try:
        response = http_session.post(url, headers=headers, json=data, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info("task created in todoist: %s", nombre_archivo)
    except Exception as e:
        logger.error("error creating task in todoist: %s", e)


def run(platform_name: str) -> None:
    """Punto de entrada callable desde el CLI sin argparse."""
    token = os.getenv("TODOIST_TOKEN")
    if not token:
        logger.error("TODOIST_TOKEN not found in .env")
        return

    prefix = f"{platform_name}_descargas_"
    log_paths = [LOG_DIR / f for f in os.listdir(LOG_DIR)
                 if f.startswith(prefix) and f.endswith(".log")]
    if not log_paths:
        logger.info("no recent download log found.")
        return

    # Ordenar por tiempo de modificación para tomar la sesión más reciente,
    # independientemente del formato del nombre de archivo.
    latest_log = max(log_paths, key=lambda p: p.stat().st_mtime)
    logger.info("sending tasks from %s to todoist...", latest_log.name)

    http_session = _build_http_session()
    try:
        with open(latest_log, "r", encoding="utf-8") as f:
            for linea in f:
                m = PATRON.match(linea.strip())
                if m is None:
                    logger.warning("unrecognized line format, skipping:\n  %s", linea.rstrip())
                    continue
                g = m.groupdict()
                crear_tarea_todoist(
                    nombre_archivo=g["archivo"],
                    curso=g["curso"],
                    semana=g["semana"],
                    tema=g["tema"],
                    token=token,
                    http_session=http_session,
                )
    finally:
        http_session.close()


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, help="nombre de la plataforma")
    args = parser.parse_args()
    run(args.platform)


if __name__ == "__main__":
    main()
