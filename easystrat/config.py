"""
Konfigurationsmodul für die EasyVerein-Strato E-Mail-Synchronisierung.

Lädt Einstellungen aus Umgebungsvariablen oder .env-Datei.
"""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Richtet das Logging ein."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Farbiges Logging wenn möglich
    try:
        import colorlog

        handler = colorlog.StreamHandler()
        handler.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                log_colors={
                    "DEBUG": "cyan",
                    "INFO": "green",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "red,bg_white",
                },
            )
        )
    except ImportError:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
        )

    logger = logging.getLogger("mail_sync")
    logger.setLevel(log_level)
    logger.addHandler(handler)

    return logger


@dataclass
class EasyVereinConfig:
    """Konfiguration für EasyVerein API."""

    api_key: str
    api_version: str = "v2.0"
    group_id: Optional[int] = None  # Optionale Gruppenfilterung (z.B. Männerchor-ID)
    group_name: Optional[str] = None  # Gruppenname für Logging


@dataclass
class StratoConfig:
    """Konfiguration für Strato ManageSieve (Legacy)."""

    host: str
    port: int
    email: str
    password: str
    sieve_script_name: str = "chor_weiterleitung"


@dataclass
class StratoWebmailConfig:
    """Konfiguration für Strato Webmail Selenium-Zugang."""

    email: str
    password: str
    webmail_url: str = "https://webmail.strato.de/"
    headless: bool = True
    browser: str = "chrome"
    timeout: int = 30
    rule_name: str = "Männerchor"  # Name der Filterregel (Legacy, für alte Single-Rule)
    rule_prefix: str = "MC_"  # Prefix für individuelle Regeln pro Mitglied
    use_individual_rules: bool = True  # True = eine Regel pro Mitglied


@dataclass
class SyncConfig:
    """Gesamtkonfiguration für die Synchronisierung."""

    easyverein: EasyVereinConfig
    strato: Optional[StratoConfig] = None
    strato_webmail: Optional[StratoWebmailConfig] = None
    dry_run: bool = True
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env_path: Optional[Path] = None) -> "SyncConfig":
        """
        Lädt die Konfiguration aus Umgebungsvariablen.

        Args:
            env_path: Optionaler Pfad zur .env-Datei

        Returns:
            SyncConfig-Instanz mit geladenen Werten

        Raises:
            ValueError: Wenn erforderliche Umgebungsvariablen fehlen
        """
        # .env-Datei laden falls vorhanden
        if env_path:
            load_dotenv(env_path)
        else:
            # Versuche .env im aktuellen Verzeichnis oder Elternverzeichnis zu finden
            current_dir = Path(__file__).resolve().parent
            possible_paths = [
                Path.cwd() / ".env",  # Aktuelles Arbeitsverzeichnis
                current_dir / ".env",  # easystrat/ Verzeichnis
                current_dir.parent / ".env",  # Projektwurzel
            ]

            for env_file in possible_paths:
                if env_file.exists():
                    load_dotenv(env_file)
                    break
            else:
                load_dotenv()  # Fallback: Standard-Verhalten

        # Erforderliche Variable prüfen (nur EasyVerein)
        required_vars = ["EV_API_KEY"]

        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(
                f"Fehlende Umgebungsvariablen: {', '.join(missing)}\n"
                "Bitte .env-Datei anlegen (siehe .env.example)"
            )

        # EasyVerein Konfiguration
        group_id_str = os.getenv("EV_GROUP_ID", "")
        easyverein = EasyVereinConfig(
            api_key=os.getenv("EV_API_KEY", ""),
            api_version=os.getenv("EV_API_VERSION", "v2.0"),
            group_id=int(group_id_str) if group_id_str else None,
            group_name=os.getenv("EV_GROUP_NAME", "Männerchor"),
        )

        # Strato ManageSieve Konfiguration (Legacy, optional)
        strato = None
        if os.getenv("STRATO_HOST") and os.getenv("STRATO_EMAIL") and os.getenv("STRATO_PASSWORD"):
            strato = StratoConfig(
                host=os.getenv("STRATO_HOST", "imap.strato.de"),
                port=int(os.getenv("STRATO_SIEVE_PORT", "4190")),
                email=os.getenv("STRATO_EMAIL", ""),
                password=os.getenv("STRATO_PASSWORD", ""),
                sieve_script_name=os.getenv("SIEVE_SCRIPT_NAME", "chor_weiterleitung"),
            )

        # Strato Webmail Konfiguration (Selenium-basiert)
        strato_webmail = None
        if os.getenv("STRATO_EMAIL") and os.getenv("STRATO_PASSWORD"):
            strato_webmail = StratoWebmailConfig(
                email=os.getenv("STRATO_EMAIL", ""),
                password=os.getenv("STRATO_PASSWORD", ""),
                webmail_url=os.getenv("STRATO_WEBMAIL_URL", "https://webmail.strato.de/"),
                headless=os.getenv("STRATO_HEADLESS", "true").lower() in ("true", "1", "yes"),
                browser=os.getenv("STRATO_BROWSER", "chrome").lower(),
                timeout=int(os.getenv("STRATO_TIMEOUT", "30")),
                rule_name=os.getenv("STRATO_RULE_NAME", "Männerchor"),
                rule_prefix=os.getenv("STRATO_RULE_PREFIX", "MC_"),
                use_individual_rules=os.getenv("STRATO_INDIVIDUAL_RULES", "true").lower() in ("true", "1", "yes"),
            )

        return cls(
            easyverein=easyverein,
            strato=strato,
            strato_webmail=strato_webmail,
            dry_run=os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


def load_config() -> SyncConfig:
    """
    Lädt und validiert die Konfiguration.

    Returns:
        Validierte SyncConfig-Instanz
    """
    try:
        config = SyncConfig.from_env()
        return config
    except ValueError as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        sys.exit(1)
