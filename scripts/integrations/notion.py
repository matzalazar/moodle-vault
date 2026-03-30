# scripts/integrations/notion.py
#
# Lee el log de descargas más reciente y crea una fila en una base de datos
# de Notion por cada archivo descargado en la sesión.
#
# Requiere una integración con permisos de escritura sobre la base de datos
# y los tokens NOTION_TOKEN / NOTION_DATABASE_ID configurados en .env.

import os
import re
import sys
import logging
import argparse
import requests
from datetime import datetime as _dt
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from dotenv import load_dotenv

from scripts.utils import setup_logging

load_dotenv()

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

logger = logging.getLogger(__name__)

# Patrón que coincide con el formato de línea escrito por registrar_descarga_log:
# [YYYY-MM-DD HH:MM:SS] Curso | Semana > Tema => archivo.ext
PATRON = re.compile(
    r"\[(?P<fecha>[^\]]+)\]\s+(?P<curso>.+?)\s+\|\s+(?P<semana>.+?)\s+>\s+(?P<tema>.+?)\s+=>\s+(?P<archivo>.+)"
)

# Nombres de propiedades de la base de datos Notion.
# Se pueden sobreescribir con variables de entorno si el esquema de la base
# difiere del recomendado en el README.
_PROP_ARCHIVO    = os.getenv("NOTION_PROP_ARCHIVO",    "Archivo")
_PROP_CURSO      = os.getenv("NOTION_PROP_CURSO",      "Curso")
_PROP_SEMANA     = os.getenv("NOTION_PROP_SEMANA",     "Semana")
_PROP_TEMA       = os.getenv("NOTION_PROP_TEMA",       "Tema")
_PROP_PLATAFORMA = os.getenv("NOTION_PROP_PLATAFORMA", "Plataforma")
_PROP_FECHA      = os.getenv("NOTION_PROP_FECHA",      "Fecha")
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


def crear_fila_notion(
    archivo: str,
    curso: str,
    semana: str,
    tema: str,
    fecha: str,
    platform: str,
    token: str,
    database_id: str,
    http_session: requests.Session,
) -> None:
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    # El log guarda la fecha con hora; la API de Notion espera solo la fecha.
    try:
        fecha_iso = _dt.fromisoformat(fecha.strip()).date().isoformat()
    except ValueError:
        logger.warning("unexpected date format: '%s'. using raw value.", fecha)
        fecha_iso = fecha.strip().split(" ")[0]

    data = {
        "parent": {"database_id": database_id},
        "properties": {
            _PROP_ARCHIVO:    {"title":     [{"text": {"content": archivo.strip()}}]},
            _PROP_CURSO:      {"rich_text": [{"text": {"content": curso.strip()}}]},
            _PROP_SEMANA:     {"rich_text": [{"text": {"content": semana.strip()}}]},
            _PROP_TEMA:       {"rich_text": [{"text": {"content": tema.strip()}}]},
            _PROP_PLATAFORMA: {"select":    {"name": platform}},
            _PROP_FECHA:      {"date":      {"start": fecha_iso}},
        },
    }

    try:
        response = http_session.post(url, headers=headers, json=data, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info("row created in notion: %s", archivo.strip())
    except Exception as e:
        logger.error("error creating row in notion: %s", e)


def run(platform_name: str) -> None:
    """Punto de entrada callable desde el CLI sin argparse."""
    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")

    if not token:
        logger.error("NOTION_TOKEN not found in .env")
        return
    if not database_id:
        logger.error("NOTION_DATABASE_ID not found in .env")
        return

    # Tomar el log más reciente para la plataforma indicada, ordenando por
    # tiempo de modificación para no depender del formato del nombre de archivo.
    prefix = f"{platform_name}_descargas_"
    log_paths = [LOG_DIR / f for f in os.listdir(LOG_DIR)
                 if f.startswith(prefix) and f.endswith(".log")]
    if not log_paths:
        logger.info("no recent download log found.")
        return

    latest_log = max(log_paths, key=lambda p: p.stat().st_mtime)
    logger.info("sending entries from %s to notion...", latest_log.name)

    http_session = _build_http_session()
    try:
        with open(latest_log, "r", encoding="utf-8") as f:
            for linea in f:
                m = PATRON.match(linea.strip())
                if m is None:
                    logger.warning("unrecognized line format, skipping:\n  %s", linea.rstrip())
                    continue
                g = m.groupdict()
                crear_fila_notion(
                    archivo=g["archivo"],
                    curso=g["curso"],
                    semana=g["semana"],
                    tema=g["tema"],
                    fecha=g["fecha"],
                    platform=platform_name,
                    token=token,
                    database_id=database_id,
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
