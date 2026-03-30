# scripts/scraper/selectors.py
#
# Selectores CSS, localizadores de Selenium y constantes de URL centralizados.
# Mantenerlos aquí en lugar de dispersarlos por los módulos facilita
# adaptarse a cambios en el markup de Moodle sin tocar la lógica de scraping.

from selenium.webdriver.common.by import By

# ── Navegación a "Mis Cursos" ─────────────────────────────────────────────────
# Moodle expone este enlace de formas distintas según tema y versión;
# se prueban en orden hasta que uno funcione.
MIS_CURSOS_CANDIDATOS = [
    (By.LINK_TEXT,         "Mis cursos"),
    (By.PARTIAL_LINK_TEXT, "Mis curso"),
    (By.CSS_SELECTOR,      'a[href*="/my/courses"]'),
    (By.CSS_SELECTOR,      'a[href*="/course/index.php?"]'),
]

# ── Lista de cursos ───────────────────────────────────────────────────────────
COURSE_LINK = "a.aalink.coursename"

# ── Estructura del curso ──────────────────────────────────────────────────────
SECTION         = "li.section.main.clearfix"
SECTION_TITLE_A = "h3.sectionname a"   # cuando el título es un enlace
SECTION_TITLE   = "h3.sectionname"     # fallback: título sin enlace
ACTIVITY        = "li.activity"
ACTIVITY_LINK   = "a.aalink"

# ── Expandir/colapsar secciones ───────────────────────────────────────────────
EXPAND_BTN      = "a.collapseexpand, [data-action='toggle-all']"
COLLAPSED_ITEMS = ".collapsed"

# ── Popups y overlays ─────────────────────────────────────────────────────────
# Moodle (y algunos temas personalizados) muestra popups de aviso en el primer
# acceso a un curso. Se intenta cerrarlos con estos selectores antes de
# interactuar con el contenido.
POPUP_CLOSE_SELECTORS = [
    "[id*='popup'] button",
    "[id*='popup'] .close",
    "[class*='popup'] button",
    "[class*='popup'] .close",
    ".modal .close",
    "button[aria-label='Close']",
    "button[data-dismiss='modal']",
]
# Usado en el fallback JS cuando ningún botón de cierre es clickeable.
POPUP_OVERLAY_JS = '[id*="popup"], [class*="popup-visible"], [class*="overlay"]'

# ── Módulos de Moodle (fragmentos de URL) ─────────────────────────────────────
MOD_URL      = "/mod/url/"       # enlace externo; puede redirigir a YouTube u otro sitio
MOD_RESOURCE = "/mod/resource/"  # archivo único embebido
MOD_FOLDER   = "/mod/folder/"    # carpeta de archivos
MOD_PAGE     = "/mod/page/"      # página HTML interna

# ── Dominios de video externos ────────────────────────────────────────────────
# Se usan para detectar si un /mod/url/ redirige a una playlist de YouTube.
YOUTUBE_DOMAINS = ("youtube.com", "youtu.be")
