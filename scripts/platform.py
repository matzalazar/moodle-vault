# scripts/platform.py
#
# Carga la configuración de cada plataforma Moodle desde su archivo JSON
# y expone los paths derivados que el resto del sistema usa directamente.
# Centralizar esto en un dataclass evita pasar strings sueltos entre módulos.

import json
import logging
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)


@dataclass
class PlatformConfig:
    name: str
    display_name: str
    login_url: str
    course_links_path: Path
    tree_dir: Path
    course_dir: Path


def load_platform(name: str) -> PlatformConfig:
    platform_file = BASE_DIR / "config" / "platforms" / f"{name}.json"
    if not platform_file.exists():
        raise FileNotFoundError(f"Plataforma no encontrada: {platform_file}")
    data = json.loads(platform_file.read_text(encoding="utf-8"))
    if "login_url" not in data:
        raise ValueError(
            f"El archivo de plataforma '{name}' no contiene el campo 'login_url'."
        )
    return PlatformConfig(
        name=name,
        display_name=data.get("display_name", name),
        login_url=data["login_url"],
        course_links_path=BASE_DIR / "config" / name / "course_links.json",
        tree_dir=BASE_DIR / "data" / name / "trees",
        course_dir=BASE_DIR / "data" / name / "course",
    )


def list_platforms() -> list[str]:
    d = BASE_DIR / "config" / "platforms"
    return [f.stem for f in d.glob("*.json")] if d.exists() else []
