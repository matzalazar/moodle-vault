"""
Typer command definitions for moodle-vault.

All commands live here so main.py stays a thin bootstrap. Each command
follows the same pattern:
  1. Configure logging
  2. Select platform (interactive or --platform)
  3. Delegate to the relevant pipeline function
  4. Surface errors cleanly (no unhandled tracebacks for expected failures)
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from loguru import logger

from scripts.platform import list_platforms, load_platform

load_dotenv()

app = typer.Typer(
    name="moodle",
    help="Automated scraping for Moodle learning platforms.",
    add_completion=False,
)

_LEVEL_SYMBOLS: dict[str, str] = {
    "DEBUG":    "[.]",
    "INFO":     "[i]",
    "SUCCESS":  "[-]",
    "WARNING":  "[!]",
    "ERROR":    "[x]",
    "CRITICAL": "[!!]",
}

_C   = typer.colors.CYAN
_DIM = typer.colors.BRIGHT_BLACK
_GR  = typer.colors.GREEN
_YE  = typer.colors.YELLOW


def _h(text: str) -> str:
    """Section header: bold."""
    return typer.style(text, bold=True)


def _dim(text: str) -> str:
    """Secondary text: dimmed."""
    return typer.style(text, fg=_DIM)


def _opt(text: str) -> str:
    """Menu option number: bold cyan."""
    return typer.style(text, fg=_C, bold=True)


def _val(text: str) -> str:
    """Highlighted value in tables: cyan."""
    return typer.style(text, fg=_C)


class _InterceptHandler(logging.Handler):
    """Routes stdlib logging through loguru for unified output."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _log_format(record: dict) -> str:
    symbol = _LEVEL_SYMBOLS.get(record["level"].name, "[?]")
    return f"<green>{{time:HH:mm:ss}}</green> <level>{symbol}</level> {{message}}\n"


def _configure_logging(verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, format=_log_format, level=level, colorize=True)
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)


def _select_platform(platform: Optional[str]) -> str:
    platforms = list_platforms()
    if not platforms:
        logger.error("No platforms found in config/platforms/. Create at least one .json file.")
        raise typer.Exit(code=1)

    if platform:
        if platform not in platforms:
            logger.error(f"Platform not found: '{platform}'")
            raise typer.Exit(code=1)
        return platform

    if len(platforms) == 1:
        logger.info(f"Platform detected: {platforms[0]}")
        return platforms[0]

    typer.echo("")
    typer.echo(_h("Available platforms"))
    typer.echo(_dim("─" * 20))
    for i, p in enumerate(platforms, start=1):
        typer.echo(f"  {_opt(f'[{i}]')} {p}")
    typer.echo("")

    choice = typer.prompt(f"Select a platform [1-{len(platforms)}]")
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(platforms)):
            raise ValueError
    except ValueError:
        logger.error(f"Invalid selection: {choice!r}")
        raise typer.Exit(code=1)

    selected = platforms[idx]
    logger.info(f"Platform selected: {selected}")
    return selected


def _prompt_rescrape() -> int:
    typer.echo("")
    typer.echo(_h("Re-scrape weeks with late-uploaded content?"))
    typer.echo(f"  {_opt('[0]')} no  {_dim('(default)')}")
    typer.echo(f"  {_opt('[1]')} last week")
    typer.echo(f"  {_opt('[2]')} last two weeks")
    typer.echo("")
    choice = typer.prompt("Option", default="0").strip()
    if choice == "1":
        return 1
    if choice == "2":
        return 2
    return 0


def _run_integrations(platform_name: str) -> None:
    import datetime

    from scripts.utils import LOG_DIR

    platform_upper = platform_name.upper()
    todoist_enabled = os.environ.get(f"{platform_upper}_TODOIST_ENABLED") == "true"
    notion_enabled = os.environ.get(f"{platform_upper}_NOTION_ENABLED") == "true"
    todoist_token = os.environ.get("TODOIST_TOKEN")
    notion_token = os.environ.get("NOTION_TOKEN")
    notion_db = os.environ.get("NOTION_DATABASE_ID")

    actual_log = LOG_DIR / f"{platform_name}_descargas_actual.log"
    if not actual_log.exists():
        logger.info("No new downloads found in this run.")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    final_log = LOG_DIR / f"{platform_name}_descargas_{timestamp}.log"
    actual_log.rename(final_log)
    logger.info(f"Download log: {final_log.name}")

    if todoist_token and todoist_enabled:
        logger.info("Sending tasks to Todoist...")
        try:
            from scripts.integrations.todoist import run as run_todoist
            run_todoist(platform_name)
        except Exception as exc:
            logger.warning(f"Todoist integration failed: {exc}")

    if notion_token and notion_db and notion_enabled:
        logger.info("Sending entries to Notion...")
        try:
            from scripts.integrations.notion import run as run_notion
            run_notion(platform_name)
        except Exception as exc:
            logger.warning(f"Notion integration failed: {exc}")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@app.command()
def run(
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="Platform name"),
    rescrape: Optional[int] = typer.Option(
        None, "--rescrape", "-r",
        help="Re-scrape recent weeks (0=no, 1=last week, 2=last two weeks)",
        min=0,
        max=2,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip interactive prompts (useful for scripts or CI)",
    ),
) -> None:
    """
    Run the full scraping pipeline.

    Selects the platform, updates course links, syncs the course tree, and
    downloads new files. Runs any enabled integrations (.env) when done.
    """
    _configure_logging(verbose)

    name = _select_platform(platform)

    rescrape_val = rescrape
    if rescrape_val is None:
        rescrape_val = 0 if yes else _prompt_rescrape()

    try:
        platform_cfg = load_platform(name)
    except Exception as exc:
        logger.error(f"Failed to load platform: {exc}")
        raise typer.Exit(code=1) from exc

    platform_cfg.course_links_path.parent.mkdir(parents=True, exist_ok=True)
    platform_cfg.tree_dir.mkdir(parents=True, exist_ok=True)
    platform_cfg.course_dir.mkdir(parents=True, exist_ok=True)

    from scripts.utils import LOG_DIR
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    actual_log = LOG_DIR / f"{name}_descargas_actual.log"
    if actual_log.exists():
        actual_log.unlink()

    logger.info(f"Starting pipeline: {platform_cfg.display_name}")

    from scripts.scraper import download_files, extract_course_tree, fetch_links
    from scripts.scraper.reset_semanas import reset_semanas_recientes
    from scripts.scraper.session import get_authenticated_browser

    try:
        browser = get_authenticated_browser(platform_cfg)
    except Exception as exc:
        logger.error(f"Failed to start browser: {exc}")
        raise typer.Exit(code=1) from exc

    try:
        fetch_links.run(browser, platform_cfg)
        extract_course_tree.run(browser, platform_cfg)
        if rescrape_val > 0:
            reset_semanas_recientes(platform_cfg.tree_dir, rescrape_val)
        download_files.run(browser, platform_cfg)
    except Exception as exc:
        logger.error(f"Pipeline error: {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        browser.quit()

    _run_integrations(name)
    logger.success("Done.")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status(
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="Platform name"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Show status of configured platforms and courses."""
    _configure_logging(verbose)

    platforms = list_platforms()
    if not platforms:
        logger.warning("No platforms found in config/platforms/.")
        return

    targets = [platform] if platform else platforms

    from scripts.utils import LOG_DIR

    for name in targets:
        try:
            cfg = load_platform(name)
        except Exception as exc:
            logger.warning(f"Could not load '{name}': {exc}")
            continue

        course_count = 0
        tracked_count = 0
        if cfg.course_links_path.exists():
            try:
                links = json.loads(cfg.course_links_path.read_text(encoding="utf-8"))
                course_count = len(links)
                tracked_count = sum(1 for c in links if c.get("seguimiento"))
            except Exception:
                pass

        tree_count = len(list(cfg.tree_dir.glob("*.json"))) if cfg.tree_dir.exists() else 0

        last_log = None
        if LOG_DIR.exists():
            prefix = f"{name}_descargas_"
            logs = [f for f in LOG_DIR.iterdir()
                    if f.name.startswith(prefix) and f.suffix == ".log"]
            if logs:
                last_log = max(logs, key=lambda p: p.stat().st_mtime)

        typer.echo(f"\n{_h(_val(cfg.display_name))}")
        typer.echo(_dim("─" * max(len(cfg.display_name), 20)))
        typer.echo(f"  {_dim('Platform        :')} {name}")
        typer.echo(f"  {_dim('Login URL       :')} {_dim(cfg.login_url)}")
        typer.echo(
            f"  {_dim('Courses         :')} {_val(str(course_count))}"
            f"  {_dim(f'({tracked_count} tracked)')}"
        )
        typer.echo(f"  {_dim('Trees           :')} {_val(str(tree_count))} {_dim('file(s)')}")
        typer.echo(
            f"  {_dim('Last download   :')} "
            + (typer.style(last_log.name, fg=_GR) if last_log else _dim("none"))
        )

    typer.echo("")


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

@app.command()
def fetch(
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="Platform name"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """
    Update available course links (stage 1).

    Opens the browser, navigates to the course list, and asks interactively
    whether each course should be tracked.
    """
    _configure_logging(verbose)

    name = _select_platform(platform)

    try:
        platform_cfg = load_platform(name)
    except Exception as exc:
        logger.error(f"Failed to load platform: {exc}")
        raise typer.Exit(code=1) from exc

    platform_cfg.course_links_path.parent.mkdir(parents=True, exist_ok=True)

    from scripts.scraper import fetch_links
    from scripts.scraper.session import get_authenticated_browser

    try:
        browser = get_authenticated_browser(platform_cfg)
    except Exception as exc:
        logger.error(f"Failed to start browser: {exc}")
        raise typer.Exit(code=1) from exc

    try:
        fetch_links.run(browser, platform_cfg)
    except Exception as exc:
        logger.error(f"Fetch error: {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        browser.quit()

    logger.success("Course links updated.")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

@app.command()
def sync(
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="Platform name"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """
    Synchronize the course tree (stage 2).

    Traverses each tracked course and rebuilds its section and topic structure,
    preserving the 'reviewed' state of already-processed topics.
    """
    _configure_logging(verbose)

    name = _select_platform(platform)

    try:
        platform_cfg = load_platform(name)
    except Exception as exc:
        logger.error(f"Failed to load platform: {exc}")
        raise typer.Exit(code=1) from exc

    platform_cfg.tree_dir.mkdir(parents=True, exist_ok=True)
    platform_cfg.course_dir.mkdir(parents=True, exist_ok=True)

    from scripts.scraper import extract_course_tree
    from scripts.scraper.session import get_authenticated_browser

    try:
        browser = get_authenticated_browser(platform_cfg)
    except Exception as exc:
        logger.error(f"Failed to start browser: {exc}")
        raise typer.Exit(code=1) from exc

    try:
        extract_course_tree.run(browser, platform_cfg)
    except Exception as exc:
        logger.error(f"Sync error: {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        browser.quit()

    logger.success("Course tree synchronized.")


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

@app.command()
def download(
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="Platform name"),
    rescrape: Optional[int] = typer.Option(
        None, "--rescrape", "-r",
        help="Re-scrape recent weeks before downloading (0=no, 1=last week, 2=last two weeks)",
        min=0,
        max=2,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the re-scraping prompt"),
) -> None:
    """
    Download new files (stages 3 and 4).

    Optionally resets recent weeks before downloading — useful when an instructor
    uploads content late. Runs enabled integrations when done.
    """
    _configure_logging(verbose)

    name = _select_platform(platform)

    rescrape_val = rescrape
    if rescrape_val is None:
        rescrape_val = 0 if yes else _prompt_rescrape()

    try:
        platform_cfg = load_platform(name)
    except Exception as exc:
        logger.error(f"Failed to load platform: {exc}")
        raise typer.Exit(code=1) from exc

    platform_cfg.tree_dir.mkdir(parents=True, exist_ok=True)
    platform_cfg.course_dir.mkdir(parents=True, exist_ok=True)

    from scripts.utils import LOG_DIR
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    actual_log = LOG_DIR / f"{name}_descargas_actual.log"
    if actual_log.exists():
        actual_log.unlink()

    from scripts.scraper import download_files
    from scripts.scraper.reset_semanas import reset_semanas_recientes
    from scripts.scraper.session import get_authenticated_browser

    try:
        browser = get_authenticated_browser(platform_cfg)
    except Exception as exc:
        logger.error(f"Failed to start browser: {exc}")
        raise typer.Exit(code=1) from exc

    try:
        if rescrape_val > 0:
            reset_semanas_recientes(platform_cfg.tree_dir, rescrape_val)
        download_files.run(browser, platform_cfg)
    except Exception as exc:
        logger.error(f"Download error: {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        browser.quit()

    _run_integrations(name)
    logger.success("Download complete.")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@app.command()
def export(
    platform: Optional[str] = typer.Option(None, "--platform", "-p", help="Platform name"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output .md file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """
    Export the course tree to a Markdown file.

    Reads the locally-stored JSON trees (no browser required) and writes a
    structured .md with every section and item title.
    """
    _configure_logging(verbose)

    name = _select_platform(platform)

    try:
        platform_cfg = load_platform(name)
    except Exception as exc:
        logger.error(f"Failed to load platform: {exc}")
        raise typer.Exit(code=1) from exc

    if not platform_cfg.tree_dir.exists():
        logger.error(f"Tree directory not found: {platform_cfg.tree_dir}")
        logger.error("Run 'sync' first to build the course tree.")
        raise typer.Exit(code=1)

    tree_files = sorted(platform_cfg.tree_dir.glob("*.json"))
    if not tree_files:
        logger.error(f"No course trees found in {platform_cfg.tree_dir}")
        raise typer.Exit(code=1)

    lines: list[str] = []
    for tree_file in tree_files:
        try:
            data = json.loads(tree_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Could not read {tree_file.name}: {exc}")
            continue

        course_name = data.get("curso", tree_file.stem)
        # Moodle sometimes repeats the title with a newline — keep only the first line.
        course_name = course_name.split("\n")[0].strip()

        lines.append(f"## {course_name}")
        lines.append("")

        for seccion in data.get("semanas", []):
            titulo = seccion.get("titulo", "(sin título)").strip()
            lines.append(f"### {titulo}")

            temas = seccion.get("temas", [])
            if temas:
                for tema in temas:
                    nombre = tema.get("nombre", "").strip()
                    if nombre:
                        lines.append(f"- {nombre}")
            lines.append("")

    if not lines:
        logger.warning("Nothing to export.")
        raise typer.Exit(code=0)

    md_content = "\n".join(lines)

    if output:
        out_path = Path(output)
    else:
        out_path = platform_cfg.tree_dir.parent / f"{name}_export.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_content, encoding="utf-8")
    logger.success(f"Exported to {out_path}")
