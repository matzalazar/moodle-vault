import json
import pytest
from pathlib import Path


@pytest.fixture
def tmp_platform_dir(tmp_path: Path) -> Path:
    """Creates a minimal platform directory structure in a temporary directory."""
    platforms_dir = tmp_path / "config" / "platforms"
    platforms_dir.mkdir(parents=True)
    config = {"display_name": "Test Platform", "login_url": "https://test.example/login"}
    (platforms_dir / "test.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "config" / "test").mkdir(parents=True)
    (tmp_path / "data" / "test" / "trees").mkdir(parents=True)
    (tmp_path / "data" / "test" / "course").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_log_line() -> str:
    """Returns a sample download log line."""
    return "[2026-03-16 18:15:30] Matemáticas | Semana 1 > Clase 1 => apuntes.pdf"


@pytest.fixture
def sample_course_links(tmp_path: Path) -> Path:
    """Creates a course_links.json file with two sample courses."""
    filepath = tmp_path / "course_links.json"
    data = [
        {"nombre": "Curso A", "url": "https://example.com/1", "seguimiento": True},
        {"nombre": "Curso B", "url": "https://example.com/2", "seguimiento": False},
    ]
    filepath.write_text(json.dumps(data), encoding="utf-8")
    return filepath
