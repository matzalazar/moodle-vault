import pytest
from scripts.scraper.download_files import (
    tipo_actividad,
    es_link_descargable,
    inferir_nombre,
    extraer_info_curso,
)


class TestTipoActividad:
    def test_mod_url(self):
        assert tipo_actividad("https://campus.example/mod/url/view.php?id=1") == "url"

    def test_mod_resource(self):
        assert tipo_actividad("https://campus.example/mod/resource/view.php?id=2") == "resource"

    def test_mod_folder(self):
        assert tipo_actividad("https://campus.example/mod/folder/view.php?id=3") == "folder"

    def test_mod_page(self):
        assert tipo_actividad("https://campus.example/mod/page/view.php?id=4") == "page"

    def test_ruta_desconocida(self):
        assert tipo_actividad("https://campus.example/some/other/path") == "other"

    def test_none(self):
        assert tipo_actividad(None) == "unknown"

    def test_string_vacio(self):
        assert tipo_actividad("") == "unknown"

    def test_prioridad_primera_coincidencia(self):
        # una URL con /mod/url/ debe ser "url", no "other"
        assert tipo_actividad("https://campus.example/mod/url/view.php") == "url"


class TestEsLinkDescargable:
    def test_pluginfile(self):
        url = "https://campus.example/pluginfile.php/123/mod_resource/content/1/doc.pdf"
        assert es_link_descargable(url) is True

    def test_extension_pdf(self):
        assert es_link_descargable("https://campus.example/files/lecture.pdf") is True

    def test_extension_ipynb(self):
        assert es_link_descargable("https://campus.example/files/notebook.ipynb") is True

    def test_extension_docx(self):
        assert es_link_descargable("https://campus.example/files/tp.docx") is True

    def test_extension_mp4(self):
        assert es_link_descargable("https://campus.example/video.mp4") is True

    def test_extension_py(self):
        assert es_link_descargable("https://campus.example/script.py") is True

    def test_extension_desconocida(self):
        assert es_link_descargable("https://campus.example/course/view.php?id=1") is False

    def test_html_no_descargable(self):
        assert es_link_descargable("https://campus.example/page.html") is False

    def test_none(self):
        assert es_link_descargable(None) is False

    def test_string_vacio(self):
        assert es_link_descargable("") is False

    def test_extension_case_insensitive(self):
        # el path se normaliza a lowercase antes de comparar
        assert es_link_descargable("https://campus.example/files/Clase.PDF") is True


class TestInferirNombre:
    def test_desde_content_disposition(self):
        headers = {"Content-Disposition": 'attachment; filename="practica1.pdf"'}
        assert inferir_nombre("https://example.com/file", "label", headers) == "practica1.pdf"

    def test_desde_content_disposition_sin_comillas(self):
        headers = {"Content-Disposition": "attachment; filename=apuntes.pdf"}
        assert inferir_nombre("https://example.com/file", "label", headers) == "apuntes.pdf"

    def test_desde_url_path(self):
        nombre = inferir_nombre("https://example.com/files/apuntes.docx", "label", None)
        assert nombre == "apuntes.docx"

    def test_url_encoded_filename(self):
        nombre = inferir_nombre("https://example.com/files/apuntes%20clase.pdf", "", None)
        assert nombre == "apuntes clase.pdf"

    def test_fallback_a_label(self):
        # URL sin extensión en el path → usa el label
        nombre = inferir_nombre("https://example.com/view?id=1", "mi label", None)
        assert nombre == "mi label"

    def test_fallback_a_archivo(self):
        # URL sin extensión y sin label → "archivo"
        nombre = inferir_nombre("https://example.com/view?id=1", "", None)
        assert nombre == "archivo"

    def test_url_con_php_retorna_nombre_php(self):
        # view.php tiene extensión → el código lo devuelve como nombre
        nombre = inferir_nombre("https://example.com/view.php?id=1", "mi label", None)
        assert nombre == "view.php"

    def test_reencoding_latin1_utf8(self):
        # Simula un header latin-1 que en realidad contiene UTF-8
        utf8_bytes = "programación.pdf".encode("utf-8")
        latin1_str = utf8_bytes.decode("latin-1")
        headers = {"Content-Disposition": f'attachment; filename="{latin1_str}"'}
        result = inferir_nombre("https://example.com/file", "", headers)
        assert result == "programación.pdf"

    def test_sin_headers(self):
        nombre = inferir_nombre("https://example.com/files/doc.pdf")
        assert nombre == "doc.pdf"

    def test_headers_vacios(self):
        nombre = inferir_nombre("https://example.com/files/doc.pdf", "", {})
        assert nombre == "doc.pdf"

    def test_content_disposition_prioridad_sobre_url(self):
        headers = {"Content-Disposition": 'attachment; filename="real.pdf"'}
        nombre = inferir_nombre("https://example.com/files/otro.pdf", "", headers)
        assert nombre == "real.pdf"


class TestExtraerInfoCurso:
    def test_formato_estandar(self):
        nombre = "2026-1ºC-373-FUNDAMENTOS DEL DISEÑO WEB-TU TECNOLOGÍAS"
        codigo, materia = extraer_info_curso(nombre)
        assert codigo == 373
        assert materia == "FUNDAMENTOS DEL DISEÑO WEB"

    def test_formato_sin_sufijo_tu(self):
        nombre = "2025-2ºC-101-ALGEBRA LINEAL"
        codigo, materia = extraer_info_curso(nombre)
        assert codigo == 101
        assert materia == "ALGEBRA LINEAL"

    def test_formato_desconocido_retorna_9999(self):
        codigo, materia = extraer_info_curso("Curso sin formato conocido")
        assert codigo == 9999
        assert materia == "Curso sin formato conocido"

    def test_string_vacio_retorna_9999(self):
        codigo, materia = extraer_info_curso("")
        assert codigo == 9999

    def test_codigo_tres_digitos(self):
        nombre = "2026-1ºC-042-INTRODUCCION A LA INFORMATICA-TU"
        codigo, _ = extraer_info_curso(nombre)
        assert codigo == 42

    def test_retorna_int(self):
        nombre = "2026-1ºC-200-MATERIA-TU"
        codigo, _ = extraer_info_curso(nombre)
        assert isinstance(codigo, int)
