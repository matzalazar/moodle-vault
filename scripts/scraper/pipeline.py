# scripts/scraper/pipeline.py
#
# Punto de entrada unificado del pipeline de scraping.
#
# Crea un único browser autenticado y lo reutiliza entre las tres etapas,
# evitando múltiples logins consecutivos que pueden ser bloqueados por Moodle.

import sys
import logging
import argparse

from scripts.platform import load_platform
from scripts.scraper.session import get_authenticated_browser
from scripts.scraper import fetch_links, extract_course_tree, download_files
from scripts.scraper.reset_semanas import reset_semanas_recientes
from scripts.utils import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, help="nombre de la plataforma")
    parser.add_argument(
        "--rescrape",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="resetear semanas recientes antes de descargar (0=no, 1=última, 2=últimas dos)",
    )
    args = parser.parse_args()

    platform = load_platform(args.platform)
    browser = get_authenticated_browser(platform)
    try:
        fetch_links.run(browser, platform)
        extract_course_tree.run(browser, platform)
        if args.rescrape > 0:
            reset_semanas_recientes(platform.tree_dir, args.rescrape)
        download_files.run(browser, platform)
    except Exception as e:
        logger.error("pipeline error: %s", e)
        sys.exit(1)
    finally:
        browser.quit()


if __name__ == "__main__":
    main()
