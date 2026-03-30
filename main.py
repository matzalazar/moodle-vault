"""
CLI bootstrap.

Punto de entrada alternativo para correr sin instalar el paquete:
  python main.py run
  python main.py status

El entry point principal (post-install) es el comando `moodle` registrado
en pyproject.toml, que invoca cli.commands:app directamente.
"""

from cli.commands import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
