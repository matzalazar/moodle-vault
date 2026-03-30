# moodle vault

<p align="center">
   <picture>
   <source media="(prefers-color-scheme: dark)" srcset="./assets/banner_dark.png">
   <source media="(prefers-color-scheme: light)" srcset="./assets/banner_light.png">
   <img alt="Moodle Vault Banner" src="./assets/banner_light.png" width="100%">
   </picture>
</p>

<p align="center">

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Selenium](https://img.shields.io/badge/selenium-4.x-43B02A?logo=selenium&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/matzalazar/moodle-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/matzalazar/moodle-vault/actions/workflows/ci.yml)

</p>

Herramienta de línea de comandos para descargar, organizar y archivar el contenido de plataformas Moodle de forma automática. Usa Selenium en modo headless para navegar la plataforma, extrae la estructura jerárquica de cada curso y descarga los archivos relevantes organizándolos localmente por curso, semana y tema.

> [English version](README.md)

## Características

- CLI Python instalable (comando `moodle`) basado en Typer — no requiere bash.
- Autenticación automática con credenciales por plataforma.
- Detección de cursos disponibles con selección interactiva de seguimiento.
- Extracción de la estructura jerárquica del curso (secciones, temas, materiales) en formato JSON.
- Descarga de archivos con extensiones relevantes (`.pdf`, `.docx`, `.ipynb`, `.py`, `.mp4`, entre otros).
- Detección de playlists de YouTube en actividades de tipo enlace externo.
- Re-scraping selectivo de semanas anteriores para contenido subido con retraso.
- Procesamiento incremental: los temas ya procesados se omiten en ejecuciones posteriores.
- Soporte para múltiples instancias Moodle mediante archivos de configuración independientes.
- Integración opcional con [Todoist](https://www.todoist.com) y [Notion](https://www.notion.so), configurable por plataforma desde `.env`.
- Registro de descargas con metadatos (fecha, curso, semana, tema, archivo).

## Capturas de pantalla

![Captura 1](assets/screenshot_1.png)
![Captura 2](assets/screenshot_2.png)

## Cómo funciona

```
moodle run
  │
  ├─ fetch         Navega a "Mis cursos" y extrae las URLs de los cursos.
  │                En la primera ejecución pregunta cuáles seguir.
  │
  ├─ sync          Por cada curso marcado, construye un árbol JSON con
  │                secciones, temas y metadatos de fechas.
  │                Cada corrida mergea con la estructura anterior,
  │                preservando el estado de los temas ya descargados.
  │
  ├─ reset         (opcional) Limpia el flag "revisado" de los temas
  │                en las últimas 1 o 2 semanas, forzando que se
  │                vuelvan a descargar en esta ejecución.
  │
  └─ download      Recorre el árbol, abre cada tema en el browser
                   y descarga los archivos encontrados. Las actividades
                   /mod/url/ se resuelven para detectar playlists de YouTube.
```

## Estructura del proyecto

```
cli/
├── __init__.py
└── commands.py            # Todos los comandos Typer (moodle run/status/fetch/sync/download)

scripts/
├── platform.py            # Dataclass PlatformConfig, load_platform(), list_platforms()
├── utils.py               # Sanitización, logging y utilidades compartidas
├── scraper/
│   ├── selectors.py       # Selectores CSS y constantes de Selenium
│   ├── session.py         # Gestión del navegador y autenticación
│   ├── fetch_links.py     # Etapa 1: extracción de URLs de cursos
│   ├── extract_course_tree.py  # Etapa 2: generación de árboles jerárquicos
│   ├── reset_semanas.py   # Etapa 3: re-scraping de semanas recientes
│   └── download_files.py  # Etapa 4: descarga de archivos
└── integrations/
    ├── todoist.py         # Integración con Todoist (opcional)
    └── notion.py          # Integración con Notion (opcional)

config/
├── platforms/
│   └── <plataforma>.json  # URL de login y nombre de la plataforma
└── <plataforma>/
    └── course_links.json  # Cursos seleccionados y configuración de seguimiento

data/
└── <plataforma>/
    ├── trees/             # Estructuras jerárquicas de cursos (JSON)
    └── course/            # Archivos descargados organizados por curso

logs/                      # Registro de descargas por sesión
tests/                     # Suite de tests unitarios (111 tests)
main.py                    # Punto de entrada alternativo (sin instalación)
pyproject.toml             # Definición del paquete y puntos de entrada
requirements.txt           # Lista plana de dependencias
```

## Requisitos

- Python 3.10+
- Google Chrome o Chromium

## Instalación

```bash
git clone https://github.com/matzalazar/moodle-vault.git
cd moodle-vault
python -m venv venv && source venv/bin/activate
pip install -e .
```

Crear el archivo de variables de entorno:

```bash
cp .env.example .env
# Editar .env con las credenciales y tokens correspondientes
```

## Configuración de plataforma

Crear un archivo en `config/platforms/<nombre>.json`:

```json
{
  "display_name": "Nombre de la plataforma",
  "login_url": "https://campus.universidad.edu/login/index.php"
}
```

Las credenciales se configuran en `.env` con el prefijo del nombre de la plataforma en mayúsculas:

```env
MIPLATAFORMA_USERNAME=usuario@email.com
MIPLATAFORMA_PASSWORD=contraseña
```

Cada plataforma tiene su propio directorio de datos en `config/<nombre>/` y `data/<nombre>/`.

## Uso

Tras la instalación, el comando `moodle` queda disponible globalmente en el entorno virtual activo.

### `moodle run` — pipeline completo

Ejecuta las cuatro etapas: fetch, sync, reset opcional y download. Al finalizar, activa las integraciones habilitadas.

```bash
moodle run
moodle run --platform miplataforma
moodle run --platform miplataforma --rescrape 1
moodle run --platform miplataforma --yes          # omite prompts interactivos (útil en CI)
moodle run --verbose
```

Opciones:

| Flag | Corto | Descripción |
|------|-------|-------------|
| `--platform` | `-p` | Nombre de la plataforma (omite el menú de selección) |
| `--rescrape` | `-r` | Re-scrapear semanas recientes: `0` = no, `1` = última semana, `2` = últimas dos semanas |
| `--verbose` | `-v` | Activar logging debug |
| `--yes` | `-y` | Omitir prompts interactivos |

### `moodle status` — información de plataformas

Muestra las plataformas configuradas, cantidad de cursos, archivos de árboles y último log de descarga. No requiere navegador.

```bash
moodle status
moodle status --platform miplataforma
```

Opciones: `--platform / -p`, `--verbose / -v`

### `moodle fetch` — solo etapa 1

Abre el navegador, navega a la lista de cursos y actualiza `course_links.json`.

```bash
moodle fetch
moodle fetch --platform miplataforma
```

Opciones: `--platform / -p`, `--verbose / -v`

### `moodle sync` — solo etapa 2

Reconstruye el árbol JSON de cada curso en seguimiento, mergeando con la estructura anterior.

```bash
moodle sync
moodle sync --platform miplataforma
```

Opciones: `--platform / -p`, `--verbose / -v`

### `moodle download` — etapas 3 y 4

Opcionalmente resetea semanas recientes y luego descarga archivos nuevos. Activa las integraciones al terminar.

```bash
moodle download
moodle download --platform miplataforma --rescrape 2
moodle download --yes
```

Opciones: `--platform / -p`, `--rescrape / -r`, `--verbose / -v`, `--yes / -y`

## Selección de cursos

Durante la primera ejecución, se pregunta curso por curso si se desea hacer seguimiento. La selección se guarda en `config/<plataforma>/course_links.json` con el campo `"seguimiento": true`.

En ejecuciones posteriores, solo se procesan los cursos marcados. Para modificar la selección, editar ese archivo manualmente.

## Re-scraping de semanas anteriores

Al ejecutar `moodle run` o `moodle download` sin `--yes`, se presenta el siguiente prompt:

```
Re-scrapear semanas con contenido subido tarde?
  [0] no  (por defecto)
  [1] última semana
  [2] últimas dos semanas

Opción [0]:
```

Al elegir `1` o `2`, se resetea el flag `revisado` de todos los temas cuya semana terminó dentro de esa ventana, forzando que `download_files` los procese nuevamente. Las semanas anteriores no se tocan. Esto es útil cuando un docente sube material con retraso y los temas ya fueron marcados como procesados en una ejecución anterior.

También es posible pasar `--rescrape 1` o `--rescrape 2` directamente para omitir el prompt.

## Integraciones

### Configuración

Las integraciones con Todoist y Notion se activan de forma independiente para cada plataforma en `.env`. Solo se ejecutan cuando la variable correspondiente está en `true`.

```env
# Tokens compartidos
TODOIST_TOKEN=tu_token_de_todoist
NOTION_TOKEN=tu_token_de_notion
NOTION_DATABASE_ID=tu_database_id

# Habilitación por plataforma
MIPLATAFORMA_TODOIST_ENABLED=true
MIPLATAFORMA_NOTION_ENABLED=false
```

### Notion

1. Crear una integración en [notion.so/my-integrations](https://www.notion.so/my-integrations).
2. Crear una base de datos con las columnas: `Archivo` (título), `Curso`, `Semana`, `Tema` (texto enriquecido), `Plataforma` (selección) y `Fecha` (fecha).
3. Compartir la base de datos con la integración.
4. Copiar el ID de la base (parte de la URL antes de `?v=`).
5. Configurar en `.env` el token, el ID y `{PLATAFORMA}_NOTION_ENABLED=true`.

Si los nombres de las columnas difieren del esquema recomendado, se pueden sobreescribir con variables de entorno opcionales:

```env
NOTION_PROP_ARCHIVO=Archivo
NOTION_PROP_CURSO=Curso
NOTION_PROP_SEMANA=Semana
NOTION_PROP_TEMA=Tema
NOTION_PROP_PLATAFORMA=Plataforma
NOTION_PROP_FECHA=Fecha
```

### Todoist

1. Obtener el token de la API en [app.todoist.com/app/settings/integrations/developer](https://app.todoist.com/app/settings/integrations/developer).
2. Configurar en `.env` el token y `{PLATAFORMA}_TODOIST_ENABLED=true`.

Por cada archivo descargado se crea una tarea con vencimiento para hoy y prioridad media.

## Tests

```bash
pytest
```

La suite contiene 131 tests que cubren todas las funciones puras de cada módulo: sanitización, carga de configuración de plataforma, inferencia de nombres de archivo, detección de tipos de actividad, merge incremental de estructuras, reset de semanas recientes, parsing de logs y comportamiento de los comandos CLI.

## Logs de ejemplo

El archivo `logs/example.log` contiene la salida de una corrida real. Los nombres de los docentes fueron reemplazados por `[DOCENTE A]` y `[DOCENTE B]`, las rutas absolutas por `/ruta/al/proyecto/`, y los IDs de URLs por `XXXXXXX`.

Este archivo se mantiene versionado como evidencia de ejecución real para portfolio. Está anonimizado y no contiene credenciales, tokens ni cookies de sesión.

## Agregar otras plataformas

Si usás Moodle en otra institución educativa y querés que se incluya como plataforma de referencia, podés [abrir un Issue](../../issues/new) en el repositorio. Incluí el nombre de la institución y la URL de login de la plataforma.

## Roadmap

- Sincronización con Google Calendar
- Notificaciones vía Telegram

## Licencia

[MIT](LICENSE)
