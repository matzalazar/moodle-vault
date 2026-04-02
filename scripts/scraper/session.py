# scripts/scraper/session.py
#
# Gestión del navegador y autenticación contra plataformas Moodle.
# El browser se inicializa headless y se reutiliza durante toda la sesión
# para evitar múltiples logins y mantener las cookies activas al descargar.

import os
import sys
import shutil
import logging

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from scripts.platform import PlatformConfig

load_dotenv()

logger = logging.getLogger(__name__)


def get_credentials(platform_name: str) -> tuple[str, str]:
    username = os.getenv(f"{platform_name.upper()}_USERNAME")
    password = os.getenv(f"{platform_name.upper()}_PASSWORD")
    if not username or not password:
        logger.error(
            "variables %s_USERNAME / _PASSWORD no encontradas en .env",
            platform_name.upper(),
        )
        sys.exit(1)
    return username, password


def _find_chrome_binary() -> str | None:
    # En distribuciones distintas (Arch, Ubuntu, Debian) el binario puede
    # llamarse de formas diferentes; se prueba cada nombre en orden.
    for name in ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"]:
        path = shutil.which(name)
        if path:
            return path
    return None


def init_browser() -> webdriver.Chrome | None:
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")

    binary = _find_chrome_binary()
    if binary:
        options.binary_location = binary

    try:
        # Selenium Manager (integrado desde 4.6) descarga y cachea el
        # chromedriver que corresponde a la versión instalada de Chrome.
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(60)
        driver.set_script_timeout(30)
        return driver
    except Exception as e:
        logger.error("error starting browser: %s", e)
        return None


def login_moodle(
    browser: webdriver.Chrome,
    username: str,
    password: str,
    login_url: str,
) -> webdriver.Chrome:
    logger.info("opening login page...")
    browser.get(login_url)

    wait = WebDriverWait(browser, 10)

    try:
        # Esperar a que el formulario sea visible e interactuable antes de
        # buscar los elementos; evita StaleElementReferenceException cuando
        # Moodle re-renderiza el DOM después de cargar sus scripts.
        wait.until(EC.visibility_of_element_located((By.ID, "username")))
    except TimeoutException:
        logger.error("login page did not load within the expected time.")
        browser.quit()
        sys.exit(1)

    try:
        # Re-buscar cada elemento justo antes de usarlo para evitar stale refs.
        wait.until(EC.element_to_be_clickable((By.ID, "username"))).send_keys(username)
        wait.until(EC.element_to_be_clickable((By.ID, "password"))).send_keys(password)
        wait.until(EC.element_to_be_clickable((By.ID, "loginbtn"))).click()

        # Moodle redirige fuera de la página de login tras un login exitoso.
        # Esperar hasta que eso ocurra; si no ocurre en 15 s, las credenciales
        # fallaron o la redirección no se completó.
        WebDriverWait(browser, 15).until(
            lambda d: "login" not in d.current_url
        )

        logger.info("login successful.")
        return browser

    except TimeoutException:
        logger.error("login failed. check your credentials in .env.")
        browser.quit()
        sys.exit(1)
    except Exception as e:
        logger.error("error during login: %s", e)
        browser.quit()
        sys.exit(1)


def get_authenticated_browser(platform: PlatformConfig) -> webdriver.Chrome:
    username, password = get_credentials(platform.name)
    browser = init_browser()
    if not browser:
        logger.error("error starting browser.")
        sys.exit(1)
    return login_moodle(browser, username, password, platform.login_url)
