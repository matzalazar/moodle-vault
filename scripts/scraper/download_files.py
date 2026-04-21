# scripts/scraper/download_files.py
#
# Tercera etapa del pipeline: recorre el árbol JSON de cada curso y descarga
# los archivos encontrados en cada tema.
#
# Los temas de tipo /mod/url/ no contienen archivos directos; se resuelve la
# redirección para detectar playlists de YouTube y guardar la URL en el árbol.
# El resto de tipos abre cada URL en una pestaña nueva, busca links descargables
# y los baja usando las cookies de sesión del browser autenticado.

import re
import json
import time
import logging
import argparse
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scripts.platform import load_platform, PlatformConfig
from scripts.scraper.session import get_authenticated_browser
from scripts.scraper.selectors import MOD_URL, MOD_RESOURCE, MOD_FOLDER, MOD_PAGE, YOUTUBE_DOMAINS
from scripts.utils import registrar_descarga_log, sanitizar_directorio, sanitizar_nombre_archivo, EXTENSIONES_CONOCIDAS, setup_logging

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = (10, 120)
_RETRY_STATUS = (429, 500, 502, 503, 504)

# Extrae el código numérico y el nombre de la materia del nombre completo del curso.
# Formato esperado: "2026-1ºC-373-NOMBRE DE LA MATERIA-TU TECNOLOGÍAS..."
PATRON_CURSO = re.compile(r"\d{4}-\d+ºC-(\d+)-(.+?)(?:-TU\b|$)")


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    return (urlparse(url).hostname or "").lower() or None


def es_dominio_moodle(url: str | None, host_moodle: str | None) -> bool:
    host = _hostname(url)
    if not host or not host_moodle:
        return False
    return host == host_moodle


def _build_http_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=_RETRY_STATUS,
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def extraer_info_curso(nombre_curso: str) -> tuple[int, str]:
    m = PATRON_CURSO.search(nombre_curso)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return 9999, nombre_curso


def tipo_actividad(url: str | None) -> str:
    if not url:
        return "unknown"
    if MOD_URL in url:
        return "url"
    if MOD_RESOURCE in url:
        return "resource"
    if MOD_FOLDER in url:
        return "folder"
    if MOD_PAGE in url:
        return "page"
    return "other"


def es_link_descargable(url: str | None) -> bool:
    if not url:
        return False
    if "pluginfile.php" in url:
        return True
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in EXTENSIONES_CONOCIDAS)


def inferir_nombre(
    url: str,
    label: str = "",
    response_headers: dict | None = None,
) -> str:
    """Determina el nombre de archivo desde Content-Disposition, la URL o el label del enlace."""
    if response_headers:
        cd = response_headers.get("Content-Disposition", "")
        if "filename=" in cd:
            nombre = cd.split("filename=")[-1].strip().strip('"\'')
            # Los headers HTTP se transmiten como latin-1; si el servidor encodificó
            # el nombre en UTF-8 (práctica común en servidores Moodle), hace falta
            # decodificarlo correctamente antes de usarlo como nombre de archivo.
            try:
                nombre = nombre.encode("latin-1").decode("utf-8")
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
            nombre = unquote(nombre)
            if nombre:
                return nombre
    path = urlparse(url).path
    nombre = unquote(path.split("/")[-1])
    if nombre and "." in nombre:
        return nombre
    return label or "archivo"


def descargar_archivo(
    url: str,
    destino_dir: str,
    nombre_sugerido: str,
    cookies: dict,
    host_moodle: str,
    http_session: requests.Session,
    timeout: tuple[int, int] = _DOWNLOAD_TIMEOUT,
) -> str | None:
    try:
        if not es_dominio_moodle(url, host_moodle):
            logger.warning("download skipped (external domain): %s", url)
            return None

        r = http_session.get(
            url,
            cookies=cookies,
            stream=True,
            allow_redirects=True,
            timeout=timeout,
        )
        r.raise_for_status()

        nombre = inferir_nombre(url, nombre_sugerido, dict(r.headers))
        nombre = sanitizar_nombre_archivo(nombre)
        destino = Path(destino_dir) / nombre

        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info("downloaded: %s", nombre)
        return nombre
    except Exception as e:
        logger.error("error downloading %s: %s", url, e)
        return None


def obtener_cookies_selenium(browser: webdriver.Chrome) -> dict[str, str]:
    # Las cookies del browser se pasan a requests para autenticar las
    # descargas directas sin necesidad de un segundo login.
    return {c["name"]: c["value"] for c in browser.get_cookies()}


def _extraer_url_inline(
    view_url: str,
    cookies: dict,
    host_moodle: str | None,
    http_session: requests.Session,
) -> str | None:
    """GET al visor HTML de un resource y busca la URL real del archivo.

    Moodle incrusta el archivo en un <object data="...">, <embed src="...">,
    <iframe src="..."> o <a href="..."> apuntando a pluginfile.php.
    Devuelve la primera URL encontrada, o None si no hay ninguna.
    """
    try:
        r = http_session.get(view_url, cookies=cookies, allow_redirects=True, timeout=_DOWNLOAD_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logger.debug("inline fallback GET failed for %s: %s", view_url, e)
        return None

    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup.find_all(["object", "embed", "iframe", "a"]):
        src = tag.get("data") or tag.get("src") or tag.get("href") or ""
        if "pluginfile.php" in src and es_dominio_moodle(src, host_moodle):
            return src
    return None


def procesar_curso(
    browser: webdriver.Chrome,
    curso_json: dict,
    curso_file_path: Path,
    course_links_path: Path,
    course_dir: Path,
    platform_name: str,
    curso_dir_nombre: str,
    http_session: requests.Session,
) -> None:
    with open(course_links_path, "r", encoding="utf-8") as f:
        all_courses = json.load(f)

    curso_nombre = curso_json.get("curso", "(sin nombre)")
    curso_entry = next((c for c in all_courses if c.get("nombre") == curso_nombre), None)
    if curso_entry is None:
        logger.warning(
            "course not found in %s, skipping: %s",
            course_links_path,
            curso_nombre,
        )
        return

    curso_url = curso_entry.get("url")
    if not curso_url:
        logger.warning("course has no URL in %s, skipping: %s", course_links_path, curso_nombre)
        return

    # Navegar al curso para que las cookies del dominio estén activas
    # antes de intentar descargar archivos alojados en ese mismo servidor.
    browser.get(curso_url)
    time.sleep(2)
    cookies = obtener_cookies_selenium(browser)
    host_moodle = _hostname(curso_url)

    for s_idx, semana in enumerate(curso_json["semanas"]):
        semana_nombre = semana.get("titulo_directorio") or sanitizar_directorio(semana["titulo"].replace("/", "-"))
        for t_idx, tema in enumerate(semana["temas"]):
            tema_nombre_raw = tema.get("nombre", "tema")
            tema_nombre = sanitizar_directorio(tema_nombre_raw)
            tema_url = tema.get("url")

            if not tema_url:
                logger.warning("topic has no url: %s", tema_nombre)
                continue

            if tema.get("revisado") is True:
                logger.debug("topic already reviewed: %s", tema_nombre)
                continue

            actividad = tipo_actividad(tema_url)

            if actividad == "url":
                # Los /mod/url/ redirigen a sitios externos. Se resuelve la
                # redirección para detectar playlists de YouTube y guardarlas
                # en el árbol; cualquier otro destino se registra y se omite.
                try:
                    browser.get(tema_url)
                    time.sleep(2)
                    final_url = browser.current_url
                    if any(d in final_url for d in YOUTUBE_DOMAINS):
                        logger.info("youtube playlist detected: %s -> %s", tema_nombre, final_url)
                        curso_json["semanas"][s_idx]["temas"][t_idx]["youtube_url"] = final_url
                    else:
                        logger.info("external link (%s...), skipping: %s", final_url[:60], tema_nombre)
                except Exception as e:
                    logger.warning("could not resolve external url '%s': %s", tema_nombre, e)
                curso_json["semanas"][s_idx]["temas"][t_idx]["revisado"] = True
                continue

            if actividad == "resource":
                # Los /mod/resource/ redirigen directamente al archivo y Chrome
                # cierra la pestaña automáticamente al disparar la descarga,
                # lo que rompe la sesión Selenium. Se resuelve la redirección
                # via HTTP y se descarga sin abrir pestaña nueva.
                #
                # Cuando Moodle está configurado para mostrar el archivo inline,
                # el HEAD no redirige a pluginfile.php sino que devuelve la página
                # HTML del visor. En ese caso se hace GET y se parsea el HTML para
                # encontrar la URL real del archivo.
                try:
                    r_head = http_session.head(
                        tema_url,
                        cookies=cookies,
                        allow_redirects=True,
                        timeout=_DOWNLOAD_TIMEOUT,
                    )
                    final_url = r_head.url
                    destino_dir = str(course_dir / curso_dir_nombre / semana_nombre / tema_nombre)
                    if es_link_descargable(final_url) and es_dominio_moodle(final_url, host_moodle):
                        label = inferir_nombre(final_url, tema_nombre, dict(r_head.headers))
                        nombre = descargar_archivo(final_url, destino_dir, label, cookies, host_moodle, http_session)
                        if nombre:
                            registrar_descarga_log(nombre, curso_json["curso"], semana["titulo"], tema_nombre_raw, platform_name)
                    else:
                        # Fallback: Moodle puede estar sirviendo el archivo dentro de
                        # un visor HTML. Se busca la URL real en object/embed/iframe/a.
                        file_url = _extraer_url_inline(tema_url, cookies, host_moodle, http_session)
                        if file_url:
                            label = inferir_nombre(file_url, tema_nombre)
                            nombre = descargar_archivo(file_url, destino_dir, label, cookies, host_moodle, http_session)
                            if nombre:
                                registrar_descarga_log(nombre, curso_json["curso"], semana["titulo"], tema_nombre_raw, platform_name)
                        else:
                            logger.warning("resource has no direct downloadable file: %s -> %s", tema_nombre, final_url)
                    curso_json["semanas"][s_idx]["temas"][t_idx]["revisado"] = True
                except Exception as e:
                    logger.error("error processing resource '%s': %s", tema_nombre, e)
                continue

            main_tab: str | None = None
            nueva_tab: str | None = None
            try:
                logger.info("processing topic: %s [%s]", tema_nombre, actividad)
                main_tab = browser.current_window_handle
                handles_antes = set(browser.window_handles)
                browser.execute_script("window.open(arguments[0]);", tema_url)
                # Esperar a que la nueva pestaña sea registrada por el browser
                # y capturar su handle de forma exacta, en lugar de asumir que
                # siempre será el último elemento de window_handles.
                WebDriverWait(browser, 5).until(
                    lambda d: len(d.window_handles) > len(handles_antes)
                )
                nueva_tab = (set(browser.window_handles) - handles_antes).pop()
                browser.switch_to.window(nueva_tab)

                WebDriverWait(browser, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "a"))
                )

                todos_los_links = browser.find_elements(By.TAG_NAME, "a")
                links_descargables = []
                for link in todos_los_links:
                    href = link.get_attribute("href")
                    if href and es_link_descargable(href):
                        if not es_dominio_moodle(href, host_moodle):
                            logger.info("external downloadable link skipped: %s", href)
                            continue
                        label = link.text.strip() or inferir_nombre(href)
                        links_descargables.append((href, label))

                destino_dir = str(course_dir / curso_dir_nombre / semana_nombre / tema_nombre)

                if not links_descargables:
                    logger.warning("no downloadable files found in '%s'", tema_nombre)
                else:
                    for archivo_url, label in links_descargables:
                        nombre = descargar_archivo(
                            archivo_url,
                            destino_dir,
                            label,
                            cookies,
                            host_moodle,
                            http_session,
                        )
                        if nombre:
                            registrar_descarga_log(nombre, curso_json["curso"], semana["titulo"], tema_nombre_raw, platform_name)

                curso_json["semanas"][s_idx]["temas"][t_idx]["revisado"] = True

                browser.close()
                browser.switch_to.window(main_tab)

            except Exception as e:
                logger.error("error processing '%s': %s", tema_nombre, e)
                try:
                    # Cerrar la nueva pestaña solo si todavía existe
                    if nueva_tab and nueva_tab in browser.window_handles:
                        browser.close()
                    # Restaurar el foco al main_tab si sigue vivo
                    if main_tab and main_tab in browser.window_handles:
                        browser.switch_to.window(main_tab)
                    elif browser.window_handles:
                        browser.switch_to.window(browser.window_handles[0])
                except Exception:
                    pass

    with open(curso_file_path, "w", encoding="utf-8") as f:
        json.dump(curso_json, f, indent=2, ensure_ascii=False)


def run(browser: webdriver.Chrome, platform: PlatformConfig) -> None:
    """Descarga archivos de cursos usando el browser provisto. No crea ni cierra el browser."""
    platform.course_dir.mkdir(parents=True, exist_ok=True)

    # Ordenar cursos por código numérico para que los directorios de descarga
    # queden numerados consistentemente entre ejecuciones (01_, 02_, ...).
    cursos_info = []
    for filepath in platform.tree_dir.glob("*.json"):
        with open(filepath, "r", encoding="utf-8") as f:
            curso_json = json.load(f)
        codigo, nombre_materia = extraer_info_curso(curso_json["curso"])
        cursos_info.append((codigo, nombre_materia, filepath, curso_json))

    cursos_info.sort(key=lambda x: x[0])

    http_session = _build_http_session()
    try:
        for idx, (codigo, nombre_materia, filepath, curso_json) in enumerate(cursos_info):
            nombre_sanitizado = sanitizar_directorio(nombre_materia, maxlen=55)
            curso_dir_nombre = f"{idx + 1:02d}_{nombre_sanitizado}"
            logger.info("processing downloads for: %s", curso_dir_nombre)
            procesar_curso(
                browser,
                curso_json,
                filepath,
                platform.course_links_path,
                platform.course_dir,
                platform.name,
                curso_dir_nombre,
                http_session,
            )
    finally:
        http_session.close()

    logger.info("download finished.")


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, help="nombre de la plataforma")
    args = parser.parse_args()

    platform = load_platform(args.platform)
    browser = get_authenticated_browser(platform)
    try:
        run(browser, platform)
    finally:
        browser.quit()


if __name__ == "__main__":
    main()
