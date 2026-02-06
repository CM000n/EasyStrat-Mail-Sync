#!/usr/bin/env python3
"""
EasyVerein-Strato E-Mail-Synchronisierung

Dieses Module dient der Abwärtskompatibilität.
Die eigentliche CLI ist in cli.py implementiert.

Verwendung:
    # Also Module (empfohlen nach Poetry-Installation):
    easystrat export
    easystrat compare strato.txt
    easystrat sync --apply

    # Direkt:
    python -m easystrat.cli export
"""

import sys


def main() -> int:
    """Leitet an die Click-CLI weiter."""
    from .cli import cli

    try:
        cli(obj={})
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
