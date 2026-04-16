import datetime
import pytest
from scripts.scraper.extract_dates import parsear_rango_semana
from scripts.scraper.extract_course_tree import merge_secciones


class TestParsearRangoSemana:
    def test_rango_valido(self):
        ini, fin = parsear_rango_semana("Semana 1: 01/03/2026 - 07/03/2026")
        assert ini == datetime.date(2026, 3, 1)
        assert fin == datetime.date(2026, 3, 7)

    def test_titulo_sin_fecha(self):
        ini, fin = parsear_rango_semana("Presentación del curso")
        assert ini is None
        assert fin is None

    def test_string_vacio(self):
        ini, fin = parsear_rango_semana("")
        assert ini is None
        assert fin is None

    def test_solo_una_fecha_no_matchea(self):
        ini, fin = parsear_rango_semana("Hasta el 15/06/2026")
        assert ini is None
        assert fin is None

    def test_rango_fin_de_anio(self):
        ini, fin = parsear_rango_semana("25/12/2025 - 31/12/2025")
        assert ini == datetime.date(2025, 12, 25)
        assert fin == datetime.date(2025, 12, 31)

    def test_rango_con_texto_alrededor(self):
        ini, fin = parsear_rango_semana("Clase del 10/04/2026 - 16/04/2026 (Semana 6)")
        assert ini == datetime.date(2026, 4, 10)
        assert fin == datetime.date(2026, 4, 16)


class TestMergeSecciones:
    def _seccion(self, titulo: str, temas: list[dict]) -> dict:
        return {
            "titulo": titulo,
            "titulo_directorio": f"01_{titulo}",
            "orden": 1,
            "fecha_inicio": None,
            "fecha_fin": None,
            "temas": temas,
        }

    def _tema(self, nombre: str, url: str, revisado: bool | None = None) -> dict:
        t: dict = {"nombre": nombre, "tipo": "", "url": url}
        if revisado is not None:
            t["revisado"] = revisado
        return t

    def test_preserva_revisado_true(self):
        anteriores = [self._seccion("S1", [self._tema("A", "https://x.com/1", revisado=True)])]
        nuevas = [self._seccion("S1", [self._tema("A", "https://x.com/1")])]
        merged = merge_secciones(nuevas, anteriores)
        assert merged[0]["temas"][0].get("revisado") is True

    def test_no_propaga_revisado_false(self):
        anteriores = [self._seccion("S1", [self._tema("A", "https://x.com/1", revisado=False)])]
        nuevas = [self._seccion("S1", [self._tema("A", "https://x.com/1")])]
        merged = merge_secciones(nuevas, anteriores)
        assert merged[0]["temas"][0].get("revisado") is not True

    def test_tema_nuevo_sin_revisado(self):
        anteriores = [self._seccion("S1", [self._tema("A", "https://x.com/1", revisado=True)])]
        nuevas = [self._seccion("S1", [
            self._tema("A", "https://x.com/1"),
            self._tema("B", "https://x.com/2"),
        ])]
        merged = merge_secciones(nuevas, anteriores)
        assert merged[0]["temas"][0].get("revisado") is True
        assert "revisado" not in merged[0]["temas"][1]

    def test_seccion_nueva_sin_anterior(self):
        anteriores: list[dict] = []
        nuevas = [self._seccion("S1", [self._tema("A", "https://x.com/1")])]
        merged = merge_secciones(nuevas, anteriores)
        assert len(merged) == 1
        assert "revisado" not in merged[0]["temas"][0]

    def test_url_distinta_no_propaga_revisado(self):
        anteriores = [self._seccion("S1", [self._tema("A", "https://x.com/OLD", revisado=True)])]
        nuevas = [self._seccion("S1", [self._tema("A", "https://x.com/NEW")])]
        merged = merge_secciones(nuevas, anteriores)
        # URL cambió → no debe propagar revisado
        assert "revisado" not in merged[0]["temas"][0]

    def test_multiples_secciones(self):
        anteriores = [
            self._seccion("S1", [self._tema("A", "https://x.com/1", revisado=True)]),
            self._seccion("S2", [self._tema("B", "https://x.com/2", revisado=True)]),
        ]
        nuevas = [
            self._seccion("S1", [self._tema("A", "https://x.com/1")]),
            self._seccion("S2", [self._tema("B", "https://x.com/2")]),
        ]
        merged = merge_secciones(nuevas, anteriores)
        assert merged[0]["temas"][0].get("revisado") is True
        assert merged[1]["temas"][0].get("revisado") is True

    def test_preserva_metadatos_de_seccion(self):
        anteriores: list[dict] = []
        nuevas = [self._seccion("S1", [])]
        nuevas[0]["fecha_inicio"] = "2026-03-01"
        nuevas[0]["orden"] = 5
        merged = merge_secciones(nuevas, anteriores)
        assert merged[0]["fecha_inicio"] == "2026-03-01"
        assert merged[0]["orden"] == 5

    def test_lista_nuevas_vacia(self):
        anteriores = [self._seccion("S1", [self._tema("A", "https://x.com/1")])]
        merged = merge_secciones([], anteriores)
        assert merged == []


class TestParsearRangoSemanaRobustez:
    def test_fecha_invalida_retorna_none(self):
        # Formato reconocido pero valores imposibles → debe retornar None sin lanzar
        ini, fin = parsear_rango_semana("99/99/9999 - 99/99/9999")
        assert ini is None
        assert fin is None

    def test_formato_iso_reconocido(self):
        ini, fin = parsear_rango_semana("2026-03-01 - 2026-03-07")
        assert ini == datetime.date(2026, 3, 1)
        assert fin == datetime.date(2026, 3, 7)

    def test_formato_mixto_no_matchea(self):
        # Un formato que no coincide con ningún patrón → None, None
        ini, fin = parsear_rango_semana("03/01/2026 - 2026-03-07")
        assert ini is None or fin is None
