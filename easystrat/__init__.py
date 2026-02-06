"""
EasyStrat Mail Sync - EasyVerein-Strato E-Mail-Synchronisierung

Exportiert E-Mail-Adressen aktiver Mitglieder aus EasyVerein und
synchronisiert sie mit Strato E-Mail-Weiterleitungen.
"""

__version__ = "1.0.0"

from .cli import cli

__all__ = ["cli", "__version__"]
