# scripts/scraper/reset_semanas.py
#
# Limpia el flag "revisado" de los temas que pertenecen a semanas recientes,
# forzando que download_files los procese en la próxima ejecución.
#
# El caso de uso típico es contenido subido con retraso por el docente:
# si la semana ya fue procesada y luego se agrega material nuevo, este script
# permite re-scrapear esas semanas sin tocar las anteriores.
#
# La ventana de re-scraping se define en semanas completas hacia atrás desde hoy.
# Una semana se considera "reciente" si su fecha_fin >= fecha de corte.

import os
import json
import logging
import argparse
import datetime
import tempfile
from pathlib import Path

from scripts.platform import load_platform
from scripts.utils import setup_logging

logger = logging.getLogger(__name__)


def reset_semanas_recientes(tree_dir: Path, semanas_atras: int) -> None:
    cutoff = datetime.date.today() - datetime.timedelta(weeks=semanas_atras)
    logger.info("resetting topics in weeks with fecha_fin >= %s", cutoff.isoformat())

    for filepath in tree_dir.glob("*.json"):
        with open(filepath, "r", encoding="utf-8") as f:
            curso_json = json.load(f)

        modificado = False
        for semana in curso_json.get("semanas", []):
            fecha_fin_str = semana.get("fecha_fin")
            if not fecha_fin_str:
                continue

            fecha_fin = datetime.date.fromisoformat(fecha_fin_str)
            if fecha_fin < cutoff:
                continue

            # Remover revisado de todos los temas de esta semana,
            # incluyendo los /mod/url/ que tienen youtube_url guardado.
            for tema in semana.get("temas", []):
                if "revisado" in tema:
                    del tema["revisado"]
                    modificado = True

        if modificado:
            # Escritura atómica: escribir en un archivo temporal en el mismo
            # directorio y luego renombrar. Si el proceso se interrumpe antes
            # del rename, el archivo original queda intacto.
            tmp_fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
                    json.dump(curso_json, tmp_f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, filepath)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.info("reset: %s", filepath.name)
        else:
            logger.debug("no changes: %s", filepath.name)


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Resetea el estado de revisado para semanas recientes."
    )
    parser.add_argument("--platform", required=True, help="nombre de la plataforma")
    parser.add_argument(
        "--semanas",
        type=int,
        required=True,
        choices=[1, 2],
        help="cantidad de semanas hacia atrás a resetear (1 o 2)",
    )
    args = parser.parse_args()

    platform = load_platform(args.platform)

    if not platform.tree_dir.exists():
        logger.warning("tree directory not found: %s", platform.tree_dir)
        return

    reset_semanas_recientes(platform.tree_dir, args.semanas)


if __name__ == "__main__":
    main()
