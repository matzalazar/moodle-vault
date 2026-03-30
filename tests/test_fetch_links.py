import json
import pytest
from pathlib import Path
from scripts.scraper.fetch_links import ya_configurado


class TestYaConfigurado:
    def test_archivo_inexistente(self, tmp_path: Path):
        assert ya_configurado(tmp_path / "noexiste.json") is False

    def test_todos_tienen_seguimiento(self, tmp_path: Path):
        filepath = tmp_path / "course_links.json"
        data = [
            {"nombre": "Curso A", "url": "https://example.com/1", "seguimiento": True},
            {"nombre": "Curso B", "url": "https://example.com/2", "seguimiento": False},
        ]
        filepath.write_text(json.dumps(data), encoding="utf-8")
        assert ya_configurado(filepath) is True

    def test_falta_campo_seguimiento(self, tmp_path: Path):
        filepath = tmp_path / "course_links.json"
        data = [{"nombre": "Curso A", "url": "https://example.com/1"}]
        filepath.write_text(json.dumps(data), encoding="utf-8")
        assert ya_configurado(filepath) is False

    def test_lista_vacia(self, tmp_path: Path):
        filepath = tmp_path / "course_links.json"
        filepath.write_text("[]", encoding="utf-8")
        # all() de iterable vacío es True
        assert ya_configurado(filepath) is True

    def test_mezcla_con_y_sin_seguimiento(self, tmp_path: Path):
        filepath = tmp_path / "course_links.json"
        data = [
            {"nombre": "Curso A", "seguimiento": True},
            {"nombre": "Curso B"},  # sin seguimiento
        ]
        filepath.write_text(json.dumps(data), encoding="utf-8")
        assert ya_configurado(filepath) is False

    def test_archivo_con_un_curso_completo(self, tmp_path: Path):
        filepath = tmp_path / "course_links.json"
        data = [{"nombre": "Único", "url": "https://x.com", "seguimiento": True}]
        filepath.write_text(json.dumps(data), encoding="utf-8")
        assert ya_configurado(filepath) is True
