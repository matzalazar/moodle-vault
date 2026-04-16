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
    username = (os.getenv(f"{platform_name.upper()}_USERNAME") or "").strip()
    password = (os.getenv(f"{platform_name.upper()}_PASSWORD") or "").strip()
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
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    # Evitar que Chromium se identifique como browser controlado por automation;
    # algunos Moodle/WAF rechazan el login si detectan el flag navigator.webdriver.
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

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
        # Usar JS para llenar los campos evita problemas de keyboard layout
        # con caracteres especiales en la contraseña (send_keys depende del
        # layout del SO y puede mapear mal ciertos símbolos).
        wait.until(EC.element_to_be_clickable((By.ID, "username")))
        wait.until(EC.element_to_be_clickable((By.ID, "password")))
        # Setear por ID directo en lugar de referencias que pueden ser stale
        browser.execute_script(
            "var u = document.getElementById('username');"
            "u.value = arguments[0];"
            "u.dispatchEvent(new Event('input', {bubbles:true}));"
            "u.dispatchEvent(new Event('change', {bubbles:true}));",
            username,
        )
        browser.execute_script(
            "var p = document.getElementById('password');"
            "p.value = arguments[0];"
            "p.dispatchEvent(new Event('input', {bubbles:true}));"
            "p.dispatchEvent(new Event('change', {bubbles:true}));",
            password,
        )
        pre_user = browser.execute_script("return document.getElementById('username').value")
        pre_pass = browser.execute_script("return document.getElementById('password').value")
        logger.info("pre-submit: user=%d chars, pass=%d chars", len(pre_user or ""), len(pre_pass or ""))
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
        current_url = browser.current_url
        logger.error("login failed (timeout). URL actual: %s", current_url)
        try:
            for selector in ("#loginerrormessage", ".loginerrors", ".alert-danger"):
                el = browser.find_elements(By.CSS_SELECTOR, selector)
                if el:
                    logger.error("mensaje de Moodle: %s", el[0].text.strip())
                    break
        except Exception:
            pass
        try:
            screenshot_path = "logs/login_debug.png"
            browser.save_screenshot(screenshot_path)
            logger.error("screenshot guardado en %s", screenshot_path)
        except Exception:
            pass
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
