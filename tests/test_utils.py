import logging
import pytest
from pathlib import Path
from datetime import datetime

import scripts.utils as utils_module
from scripts.utils import sanitizar_directorio, sanitizar_nombre_archivo, registrar_descarga_log, setup_logging


class TestSanitizarDirectorio:
    def test_remueve_tildes(self):
        assert sanitizar_directorio("Álgebra Lineal") == "Algebra_Lineal"

    def test_remueve_tildes_multiples(self):
        assert sanitizar_directorio("Programación y Diseño") == "Programacion_y_Diseno"

    def test_reemplaza_caracteres_invalidos(self):
        resultado = sanitizar_directorio("Semana 1: Intro/Fundamentos")
        assert "/" not in resultado
        assert ":" not in resultado

    def test_colapsa_underscores_multiples(self):
        resultado = sanitizar_directorio("Tema   con   espacios")
        assert "__" not in resultado

    def test_strips_underscores_extremos(self):
        resultado = sanitizar_directorio("  hola mundo  ")
        assert not resultado.startswith("_")
        assert not resultado.endswith("_")

    def test_respeta_maxlen(self):
        nombre_largo = "A" * 100
        assert len(sanitizar_directorio(nombre_largo, maxlen=20)) <= 20

    def test_maxlen_default(self):
        nombre_largo = "B" * 100
        assert len(sanitizar_directorio(nombre_largo)) <= 60

    def test_preserva_guiones(self):
        resultado = sanitizar_directorio("Clase-01-Introduccion")
        assert "-" in resultado

    def test_string_vacio(self):
        resultado = sanitizar_directorio("")
        assert resultado == ""

    def test_solo_caracteres_invalidos(self):
        resultado = sanitizar_directorio("!@#$%")
        assert resultado == ""


class TestSanitizarNombreArchivo:
    def test_preserva_extension_pdf(self):
        resultado = sanitizar_nombre_archivo("apuntes clase 1.pdf")
        assert resultado.endswith(".pdf")

    def test_preserva_extension_ipynb(self):
        resultado = sanitizar_nombre_archivo("practica_01.ipynb")
        assert resultado.endswith(".ipynb")

    def test_preserva_extension_docx(self):
        resultado = sanitizar_nombre_archivo("Trabajo Práctico.docx")
        assert resultado.endswith(".docx")

    def test_sanitiza_el_stem(self):
        resultado = sanitizar_nombre_archivo("Clase: Introducción.pdf")
        assert ":" not in resultado
        assert resultado.endswith(".pdf")

    def test_extension_desconocida_sanitiza_todo(self):
        # sin extensión reconocida, sanitiza el nombre entero
        resultado = sanitizar_nombre_archivo("archivo.xyz")
        assert isinstance(resultado, str)
        assert len(resultado) > 0

    def test_respeta_maxlen(self):
        nombre = "A" * 90 + ".pdf"
        resultado = sanitizar_nombre_archivo(nombre, maxlen=20)
        assert len(resultado) <= 20

    def test_nombre_sin_extension(self):
        resultado = sanitizar_nombre_archivo("archivosinextension")
        assert isinstance(resultado, str)


class TestRegistrarDescargaLog:
    def test_crea_archivo_log(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(utils_module, "LOG_DIR", tmp_path)
        registrar_descarga_log("apuntes.pdf", "Matemáticas", "Semana 1", "Clase 1", "test")
        log_file = tmp_path / "test_descargas_actual.log"
        assert log_file.exists()

    def test_escribe_todos_los_campos(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(utils_module, "LOG_DIR", tmp_path)
        registrar_descarga_log("notas.pdf", "Física", "Semana 3", "Ondas", "campus")
        contenido = (tmp_path / "campus_descargas_actual.log").read_text(encoding="utf-8")
        assert "notas.pdf" in contenido
        assert "Física" in contenido
        assert "Semana 3" in contenido
        assert "Ondas" in contenido

    def test_formato_correcto(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(utils_module, "LOG_DIR", tmp_path)
        registrar_descarga_log("doc.pdf", "Curso A", "Sem 1", "Tema 1", "plat")
        linea = (tmp_path / "plat_descargas_actual.log").read_text(encoding="utf-8").strip()
        # formato: [YYYY-MM-DD HH:MM:SS] Curso | Semana > Tema => Archivo
        assert linea.startswith("[")
        assert " | " in linea
        assert " > " in linea
        assert " => " in linea

    def test_append_multiple_entradas(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(utils_module, "LOG_DIR", tmp_path)
        registrar_descarga_log("a.pdf", "Curso", "S1", "T1", "p")
        registrar_descarga_log("b.pdf", "Curso", "S1", "T2", "p")
        lineas = (tmp_path / "p_descargas_actual.log").read_text(encoding="utf-8").splitlines()
        assert len(lineas) == 2

    def test_crea_directorio_si_no_existe(self, tmp_path: Path, monkeypatch):
        log_dir = tmp_path / "nuevos" / "logs"
        monkeypatch.setattr(utils_module, "LOG_DIR", log_dir)
        registrar_descarga_log("x.pdf", "C", "S", "T", "p")
        assert (log_dir / "p_descargas_actual.log").exists()


class TestSetupLogging:
    def test_no_duplica_handlers(self):
        root = logging.getLogger()
        saved = root.handlers[:]
        root.handlers.clear()
        setup_logging()
        setup_logging()
        count = len(root.handlers)
        root.handlers[:] = saved
        assert count == 1

    def test_preserva_handlers_existentes(self):
        root = logging.getLogger()
        saved = root.handlers[:]
        custom = logging.NullHandler()
        root.handlers[:] = [custom]
        setup_logging()
        result = list(root.handlers)
        root.handlers[:] = saved
        # setup_logging no debe borrar el handler que ya existía
        assert custom in result
