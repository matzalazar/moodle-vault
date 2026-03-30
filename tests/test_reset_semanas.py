import json
import datetime
import pytest
from pathlib import Path

from scripts.scraper.reset_semanas import reset_semanas_recientes


def _tree(semanas: list[dict]) -> dict:
    return {"curso": "Curso Test", "semanas": semanas}


def _semana(fecha_fin: str, temas: list[dict]) -> dict:
    return {
        "titulo": "Semana test",
        "titulo_directorio": "01_Semana_test",
        "orden": 1,
        "fecha_inicio": None,
        "fecha_fin": fecha_fin,
        "temas": temas,
    }


def _tema(nombre: str, revisado: bool | None = None) -> dict:
    t: dict = {"nombre": nombre, "tipo": "", "url": f"https://x.com/{nombre}"}
    if revisado is not None:
        t["revisado"] = revisado
    return t


class TestResetSemanasRecientes:
    def _write(self, tree_dir: Path, data: dict) -> Path:
        p = tree_dir / "curso_test.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_resetea_semana_dentro_de_ventana(self, tmp_path: Path):
        # semana que terminó hace 3 días → dentro de la ventana de 1 semana
        fecha_fin = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
        data = _tree([_semana(fecha_fin, [_tema("A", revisado=True)])])
        self._write(tmp_path, data)

        reset_semanas_recientes(tmp_path, semanas_atras=1)

        result = json.loads((tmp_path / "curso_test.json").read_text())
        assert "revisado" not in result["semanas"][0]["temas"][0]

    def test_no_resetea_semana_fuera_de_ventana(self, tmp_path: Path):
        # semana que terminó hace 20 días → fuera de la ventana de 1 semana
        fecha_fin = (datetime.date.today() - datetime.timedelta(days=20)).isoformat()
        data = _tree([_semana(fecha_fin, [_tema("A", revisado=True)])])
        self._write(tmp_path, data)

        reset_semanas_recientes(tmp_path, semanas_atras=1)

        result = json.loads((tmp_path / "curso_test.json").read_text())
        assert result["semanas"][0]["temas"][0].get("revisado") is True

    def test_ventana_dos_semanas_incluye_mas_semanas(self, tmp_path: Path):
        fecha_reciente = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
        fecha_anterior = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
        data = _tree([
            _semana(fecha_reciente, [_tema("A", revisado=True)]),
            _semana(fecha_anterior, [_tema("B", revisado=True)]),
        ])
        self._write(tmp_path, data)

        reset_semanas_recientes(tmp_path, semanas_atras=2)

        result = json.loads((tmp_path / "curso_test.json").read_text())
        assert "revisado" not in result["semanas"][0]["temas"][0]
        assert "revisado" not in result["semanas"][1]["temas"][0]

    def test_no_toca_temas_sin_revisado(self, tmp_path: Path):
        fecha_fin = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        data = _tree([_semana(fecha_fin, [_tema("A")])])  # sin revisado
        self._write(tmp_path, data)

        reset_semanas_recientes(tmp_path, semanas_atras=1)

        result = json.loads((tmp_path / "curso_test.json").read_text())
        assert "revisado" not in result["semanas"][0]["temas"][0]

    def test_semana_sin_fecha_fin_no_falla(self, tmp_path: Path):
        data = _tree([{
            "titulo": "Presentación",
            "titulo_directorio": "00_Presentacion",
            "orden": 0,
            "fecha_inicio": None,
            "fecha_fin": None,
            "temas": [_tema("Intro", revisado=True)],
        }])
        self._write(tmp_path, data)

        # No debe lanzar excepción y no debe modificar nada
        reset_semanas_recientes(tmp_path, semanas_atras=1)

        result = json.loads((tmp_path / "curso_test.json").read_text())
        assert result["semanas"][0]["temas"][0].get("revisado") is True

    def test_directorio_vacio_no_falla(self, tmp_path: Path):
        # No hay JSONs → debe completar sin error
        reset_semanas_recientes(tmp_path, semanas_atras=1)

    def test_multiples_cursos(self, tmp_path: Path):
        fecha_fin = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        for nombre in ["cursoA", "cursoB"]:
            data = _tree([_semana(fecha_fin, [_tema("T", revisado=True)])])
            (tmp_path / f"{nombre}.json").write_text(json.dumps(data), encoding="utf-8")

        reset_semanas_recientes(tmp_path, semanas_atras=1)

        for nombre in ["cursoA", "cursoB"]:
            result = json.loads((tmp_path / f"{nombre}.json").read_text())
            assert "revisado" not in result["semanas"][0]["temas"][0]

    def test_escritura_atomica_preserva_original_en_fallo(self, tmp_path: Path):
        from unittest.mock import patch
        fecha_fin = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        data = _tree([_semana(fecha_fin, [_tema("A", revisado=True)])])
        p = self._write(tmp_path, data)
        original_content = p.read_text()

        with patch("os.replace", side_effect=OSError("disco lleno")):
            with pytest.raises(OSError):
                reset_semanas_recientes(tmp_path, semanas_atras=1)

        # El archivo original debe estar intacto
        assert p.read_text() == original_content
        # No deben quedar archivos .tmp huérfanos
        assert list(tmp_path.glob("*.tmp")) == []
