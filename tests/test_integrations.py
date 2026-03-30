import pytest
from scripts.integrations.notion import PATRON as NOTION_PATRON
from scripts.integrations.todoist import PATRON as TODOIST_PATRON


class TestNotionLogPattern:
    def test_linea_valida(self):
        linea = "[2026-03-16 18:15:30] Matemáticas | Semana 1 > Clase 1 => apuntes.pdf"
        m = NOTION_PATRON.match(linea)
        assert m is not None
        assert m.group("fecha") == "2026-03-16 18:15:30"
        assert m.group("curso") == "Matemáticas"
        assert m.group("semana") == "Semana 1"
        assert m.group("tema") == "Clase 1"
        assert m.group("archivo") == "apuntes.pdf"

    def test_linea_invalida(self):
        assert NOTION_PATRON.match("esto no es una línea válida") is None

    def test_campos_multipalabra(self):
        linea = "[2026-01-01 00:00:00] Diseño Web Avanzado | Semana 3: Práctica > Intro HTML => clase_intro.pdf"
        m = NOTION_PATRON.match(linea)
        assert m is not None
        assert m.group("curso") == "Diseño Web Avanzado"
        assert m.group("semana") == "Semana 3: Práctica"
        assert m.group("tema") == "Intro HTML"

    def test_nombre_archivo_con_espacios(self):
        linea = "[2026-03-01 10:00:00] Física | S1 > T1 => apuntes de clase.pdf"
        m = NOTION_PATRON.match(linea)
        assert m is not None
        assert m.group("archivo") == "apuntes de clase.pdf"

    def test_linea_sin_fecha(self):
        linea = "Matemáticas | Semana 1 > Clase 1 => apuntes.pdf"
        assert NOTION_PATRON.match(linea) is None

    def test_linea_sin_separador_pipe(self):
        linea = "[2026-03-16 10:00:00] Matemáticas Semana 1 > Clase 1 => apuntes.pdf"
        assert NOTION_PATRON.match(linea) is None

    def test_nombre_archivo_extension_multiple(self):
        linea = "[2026-03-10 09:30:00] Programación | S2 > TP1 => tp1_v2.final.ipynb"
        m = NOTION_PATRON.match(linea)
        assert m is not None
        assert m.group("archivo") == "tp1_v2.final.ipynb"


class TestTodoistLogPattern:
    """El patrón de todoist debe ser equivalente al de notion."""

    def test_extrae_todos_los_campos(self):
        linea = "[2026-03-16 10:00:00] Álgebra | Semana 2 > Práctica 1 => ejercicios.pdf"
        m = TODOIST_PATRON.match(linea)
        assert m is not None
        assert m.group("archivo") == "ejercicios.pdf"
        assert m.group("curso") == "Álgebra"
        assert m.group("semana") == "Semana 2"
        assert m.group("tema") == "Práctica 1"

    def test_linea_invalida(self):
        assert TODOIST_PATRON.match("línea sin formato") is None

    def test_mismo_comportamiento_que_notion(self):
        linea = "[2026-06-01 12:00:00] Curso A | Sem 1 > Tema X => archivo.pdf"
        m_notion = NOTION_PATRON.match(linea)
        m_todoist = TODOIST_PATRON.match(linea)
        assert (m_notion is None) == (m_todoist is None)
        if m_notion and m_todoist:
            assert m_notion.groupdict() == m_todoist.groupdict()
