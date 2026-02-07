"""
Strato Webmail Selenium Client für die Verwaltung von E-Mail-Weiterleitungen.

Automatisiert das Strato Webmail (Open-Xchange) um Weiterleitungen zu verwalten.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Set

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@dataclass
class StratoWebmailConfig:
    """Konfiguration für Strato Webmail Zugang."""

    email: str
    password: str
    webmail_url: str = "https://webmail.strato.de/"
    headless: bool = True
    browser: str = "chrome"
    timeout: int = 30
    rule_name: str = "Maennerchor"  # Name der Filterregel (Legacy)
    rule_prefix: str = "MC_"  # Prefix für individuelle Regeln pro Mitglied
    use_individual_rules: bool = True  # True = eine Regel pro Mitglied


class StratoSeleniumClient:
    """
    Selenium-basierter Client für Strato Webmail.

    Automatisiert das Open-Xchange Webmail um Weiterleitungen zu verwalten.

    HINWEIS: Dieser Client ist abhängig von der UI-Struktur des Strato Webmail.
    Bei Layout-Änderungen durch Strato kann eine Anpassung nötig sein.
    """

    def __init__(self, config: StratoWebmailConfig, logger: Optional[logging.Logger] = None):
        """
        Initialisiert den Selenium Client.

        Args:
            config: Konfiguration mit Zugangsdaten
            logger: Optionaler Logger
        """
        self.config = config
        self.logger = logger or logging.getLogger("mail_sync.strato_selenium")
        self.driver: Optional[webdriver.Chrome | webdriver.Firefox] = None
        self._logged_in = False

    def _create_driver(self):
        """Erstellt den WebDriver."""
        if self.config.browser.lower() == "firefox":
            options = FirefoxOptions()
            if self.config.headless:
                options.add_argument("--headless")
            options.add_argument("--width=1920")
            options.add_argument("--height=1080")
            self.driver = webdriver.Firefox(options=options)
        else:
            # Chrome also Standard
            options = ChromeOptions()
            if self.config.headless:
                options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            # Deutsch also Sprache
            options.add_argument("--lang=de-DE")
            self.driver = webdriver.Chrome(options=options)

        self.driver.implicitly_wait(10)
        self.logger.debug(f"WebDriver erstellt ({self.config.browser})")

    def _wait_and_find(self, by: By, value: str, timeout: int = None, clickable: bool = False):
        """Wartet auf ein Element und gibt es zurück."""
        timeout = timeout or self.config.timeout
        wait = WebDriverWait(self.driver, timeout)

        if clickable:
            return wait.until(EC.element_to_be_clickable((by, value)))
        return wait.until(EC.presence_of_element_located((by, value)))

    def _wait_and_click(self, by: By, value: str, timeout: int = None):
        """Wartet auf ein Element und klickt es an."""
        element = self._wait_and_find(by, value, timeout, clickable=True)
        try:
            element.click()
        except ElementClickInterceptedException:
            # Fallback: JavaScript click
            self.driver.execute_script("arguments[0].click();", element)
        return element

    def _safe_click(self, element):
        """Klickt ein Element sicher an mit Scroll und Fallbacks."""
        try:
            # Erst zum Element scrollen
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element
            )
            time.sleep(0.3)

            # Warten bis Element sichtbar ist
            WebDriverWait(self.driver, 5).until(EC.visibility_of(element))
            element.click()
        except (
            ElementClickInterceptedException,
            ElementNotInteractableException,
            TimeoutException,
        ):
            # Fallback: JavaScript Click
            self.driver.execute_script("arguments[0].click();", element)

    def _safe_send_keys(self, element, text: str):
        """Gibt Text sicher in ein Element ein mit Scroll und Fallbacks."""
        try:
            # Erst zum Element scrollen
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element
            )
            time.sleep(0.3)

            # Warten bis Element sichtbar ist
            WebDriverWait(self.driver, 5).until(EC.visibility_of(element))
            element.clear()
            element.send_keys(text)
        except (ElementNotInteractableException, TimeoutException):
            # Fallback: JavaScript-basierte Eingabe
            self.driver.execute_script(
                "arguments[0].value = arguments[1]; "
                "arguments[0].dispatchEvent(new Event('input', {bubbles: true})); "
                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                element,
                text,
            )

    def connect(self) -> bool:
        """
        Erstellt WebDriver und loggt sich ein.

        Returns:
            True bei erfolgreicher Anmeldung
        """
        self.logger.info("Verbinde mit Strato Webmail...")

        try:
            self._create_driver()
            return self._login()
        except Exception as e:
            self.logger.error(f"Verbindungsfehler: {e}")
            self.disconnect()
            return False

    def _login(self) -> bool:
        """
        Meldet sich im Strato Webmail an.

        Returns:
            True bei erfolgreicher Anmeldung
        """
        self.logger.info(f"Öffne {self.config.webmail_url}...")
        self.driver.get(self.config.webmail_url)

        try:
            # Warte auf Login-Formular
            self.logger.debug("Warte auf Login-Formular...")

            # E-Mail-Feld finden und ausfüllen - Strato OX spezifische IDs
            email_field = self._wait_and_find(
                By.CSS_SELECTOR,
                '#io-ox-login-username, input[name="username"], input[type="email"]',
                timeout=20,
            )
            email_field.clear()
            email_field.send_keys(self.config.email)
            self.logger.debug("E-Mail eingegeben")

            # Passwort-Feld
            password_field = self._wait_and_find(
                By.CSS_SELECTOR,
                '#io-ox-login-password, input[name="password"], input[type="password"]',
            )
            password_field.clear()
            password_field.send_keys(self.config.password)
            self.logger.debug("Passwort eingegeben")

            # Login-Button - Strato OX spezifisch
            login_button = self._wait_and_find(
                By.CSS_SELECTOR,
                '#io-ox-login-button, button[type="submit"], input[type="submit"]',
                clickable=True,
            )
            self._safe_click(login_button)
            self.logger.debug("Login-Button geklickt")

            # Warte auf erfolgreichen Login (Posteingang oder Dashboard)
            time.sleep(3)  # Kurze Pause für Seitenaufbau

            # Prüfe ob Login erfolgreich war
            # Open-Xchange zeigt nach Login typischerweise die Mail-App
            try:
                WebDriverWait(self.driver, 20).until(
                    lambda d: "appsuite" in d.current_url.lower()
                    or d.find_elements(By.CSS_SELECTOR, ".folder-tree, .mail-item, .io-ox-mail")
                )
                self._logged_in = True
                self.logger.info("✅ Login erfolgreich")
                return True
            except TimeoutException:
                # Prüfe auf Fehlermeldung
                error_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, '.alert-danger, .error-message, .login-error, [class*="error"]'
                )
                if error_elements:
                    self.logger.error(f"Login fehlgeschlagen: {error_elements[0].text}")
                else:
                    self.logger.error("Login fehlgeschlagen (Timeout)")
                return False

        except TimeoutException as e:
            self.logger.error(f"Timeout beim Login: {e}")
            # Debug: Screenshot und HTML speichern
            try:
                self.driver.save_screenshot("debug_login_timeout.png")
                with open("debug_login_page.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                self.logger.debug(
                    "Debug-Dateien gespeichert: debug_login_timeout.png, debug_login_page.html"
                )
            except Exception:
                pass
            return False
        except Exception as e:
            self.logger.error(f"Login-Fehler: {e}")
            return False

    def _navigate_to_mail_filter(self) -> bool:
        """
        Navigiert zu den E-Mail-Filtereinstellungen.

        In Open-Xchange: Einstellungen → Mail → Filterregeln

        Returns:
            True wenn Navigation erfolgreich
        """
        self.logger.info("Navigiere zu Filtereinstellungen...")

        # Debug: Screenshot nach Login
        try:
            self.driver.save_screenshot("debug_after_login.png")
            with open("debug_after_login.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            self.logger.debug("Debug nach Login gespeichert")
        except Exception:
            pass

        try:
            # Strato OX Webmail: Einstellungen-Dropdown öffnen
            # Das Zahnrad-Icon ist in einem Dropdown under ID io-ox-topbar-settings-dropdown-icon

            settings_dropdown = self._wait_and_find(
                By.CSS_SELECTOR,
                '#io-ox-topbar-settings-dropdown-icon button[aria-label="Einstellungen"]',
                timeout=10,
                clickable=True,
            )
            self._safe_click(settings_dropdown)
            self.logger.debug("Einstellungen-Dropdown geöffnet")
            time.sleep(1)

            # Screenshot nach Dropdown
            try:
                self.driver.save_screenshot("debug_settings_dropdown.png")
                with open("debug_settings_dropdown.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
            except Exception:
                pass

            # Warte auf Dropdown-Menü und klicke auf "Alle Einstellungen" oder navigiere direkt
            try:
                # Versuche "Alle Einstellungen" zu finden
                all_settings = self._wait_and_find(
                    By.XPATH,
                    "//a[contains(text(), 'Alle Einstellungen')] | //a[contains(text(), 'All settings')]",
                    timeout=5,
                    clickable=True,
                )
                self._safe_click(all_settings)
                self.logger.debug("'Alle Einstellungen' geklickt")
            except TimeoutException:
                # Alternative: Direkte URL zu Einstellungen
                self.logger.debug("Versuche direkte Navigation zu Einstellungen...")
                self.driver.get(
                    f"{self.config.webmail_url}appsuite/#!!&app=io.ox/settings&folder=virtual/settings/io.ox/mail/settings/filter"
                )

            time.sleep(3)

            # Screenshot nach Settings-Navigation
            try:
                self.driver.save_screenshot("debug_after_settings.png")
                with open("debug_after_settings.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
            except Exception:
                pass

            # Jetzt sollten wir in den Einstellungen sein
            # Navigiere DIREKT via URL zu den Filterregeln
            self.logger.debug("Navigiere direkt zu Mail-Filterregeln per URL...")
            self.driver.get(
                f"{self.config.webmail_url}appsuite/#!!&app=io.ox/settings&folder=virtual/settings/io.ox/mail/settings/filter"
            )
            time.sleep(4)

            # Screenshot der Filteransicht
            try:
                self.driver.save_screenshot("debug_filter_view.png")
                with open("debug_filter_view.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                self.logger.debug("Filter-Debug gespeichert")
            except Exception:
                pass

            # Prüfe ob wir auf der Filter-Seite sind
            if (
                "filter" in self.driver.current_url.lower()
                or "filterregel" in self.driver.page_source.lower()
                or "mail filter" in self.driver.page_source.lower()
            ):
                self.logger.debug("Filterregeln-Seite erreicht")

                # Klicke auf den "Regeln" Abschnitt um ihn aufzuklappen
                try:
                    rules_section = self._wait_and_find(
                        By.CSS_SELECTOR,
                        'details[data-section-id="RULES"] summary, details[data-section="io.ox/mail/settings/rules"] summary',
                        timeout=5,
                        clickable=True,
                    )
                    self._safe_click(rules_section)
                    self.logger.debug("Regeln-Abschnitt aufgeklappt")
                    time.sleep(2)
                except TimeoutException:
                    self.logger.debug("Regeln-Abschnitt nicht gefunden oder bereits aufgeklappt")

                return True

            self.logger.warning("Konnte Filterregeln nicht finden")
            return False

        except Exception as e:
            self.logger.error(f"Fehler bei Navigation: {e}")
            return False

    def get_forwarding_addresses(self) -> Set[str]:
        """
        Liest die aktuell konfigurierten Weiterleitungsadressen aus der Mail-Regel.

        Returns:
            Set mit E-Mail-Adressen
        """
        if not self._logged_in:
            if not self.connect():
                return set()

        emails: Set[str] = set()

        try:
            if not self._navigate_to_mail_filter():
                self.logger.error("Konnte nicht zu Filterregeln navigieren")
                return set()

            time.sleep(2)

            # Suche nach der spezifischen Filterregel
            rule_name = self.config.rule_name
            self.logger.debug(f"Suche Filterregel: {rule_name}")

            # Find die Regel in der Liste und klicke auf Bearbeiten
            try:
                # Method 1: Suche nach dem Regelnamen und klicke darauf
                rule_element = self._wait_and_find(
                    By.XPATH,
                    f"//div[contains(@class, 'rule') or contains(@class, 'list-item')]//span[contains(text(), '{rule_name}')] | //li[contains(text(), '{rule_name}')]",
                    timeout=10,
                )
                self._safe_click(rule_element)
                self.logger.debug(f"Regel '{rule_name}' ausgewählt")
                time.sleep(1)
            except TimeoutException:
                self.logger.warning(
                    f"Regel '{rule_name}' nicht direkt gefunden, durchsuche Seite..."
                )

            # Klicke auf Bearbeiten-Button
            try:
                edit_button = self._wait_and_find(
                    By.XPATH,
                    "//button[contains(text(), 'Bearbeiten')] | //a[contains(text(), 'Bearbeiten')] | //button[contains(@aria-label, 'Bearbeiten')] | //button[contains(@title, 'Bearbeiten')]",
                    timeout=5,
                    clickable=True,
                )
                self._safe_click(edit_button)
                self.logger.debug("Bearbeiten-Button geklickt")
                time.sleep(2)
            except TimeoutException:
                self.logger.debug("Kein Bearbeiten-Button gefunden, versuche Doppelklick auf Regel")
                # Versuche Doppelklick auf die Regel
                try:
                    from selenium.webdriver.common.action_chains import ActionChains

                    rule_element = self._wait_and_find(
                        By.XPATH, f"//*[contains(text(), '{rule_name}')]", timeout=5
                    )
                    ActionChains(self.driver).double_click(rule_element).perform()
                    time.sleep(2)
                except Exception:
                    pass

            # Debug: Screenshot nach Regel-Bearbeitung
            try:
                self.driver.save_screenshot("debug_rule_edit.png")
                with open("debug_rule_edit.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                self.logger.debug("Regel-Bearbeitung-Debug gespeichert")
            except Exception:
                pass

            # Warte auf das Modal-Fenster mit den Umleitungsfeldern
            time.sleep(3)

            # Extrahiere E-Mail-Adressen aus den Umleitungs-Input-Feldern
            # Die Felder haben IDs wie redirect_601, redirect_607, etc.
            try:
                redirect_inputs = self.driver.find_elements(
                    By.CSS_SELECTOR, 'input[id^="redirect_"], input[name="to"]'
                )
                self.logger.debug(f"{len(redirect_inputs)} Umleitungs-Eingabefelder gefunden")

                for input_field in redirect_inputs:
                    try:
                        value = input_field.get_attribute("value")
                        if value and "@" in value:
                            email_lower = value.lower().strip()
                            # Ignoriere die eigene Address
                            if email_lower != self.config.email.lower():
                                emails.add(email_lower)
                                self.logger.debug(f"Umleitungsadresse gefunden: {email_lower}")
                    except Exception:
                        continue
            except Exception as e:
                self.logger.debug(f"Fehler beim Lesen der Input-Felder: {e}")

            self.logger.info(f"{len(emails)} Weiterleitungsadressen gefunden")

            # Schließe den Dialog wenn often
            try:
                close_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    'button.close, button[aria-label="Schließen"], .modal-header button',
                )
                self._safe_click(close_btn)
            except Exception:
                pass

        except Exception as e:
            self.logger.error(f"Fehler beim Lesen der Weiterleitungen: {e}")

        return emails

    def open_rule_for_editing(self) -> bool:
        """
        Öffnet die Filterregel für Bearbeitung.

        Returns:
            True wenn der Bearbeitungs-Dialog geöffnet wurde
        """
        self.logger.info(f"Öffne Regel '{self.config.rule_name}' zur Bearbeitung...")

        try:
            if not self._navigate_to_mail_filter():
                return False

            time.sleep(2)

            rule_name = self.config.rule_name

            # Find die Regel und klicke darauf
            try:
                rule_element = self._wait_and_find(
                    By.XPATH,
                    f"//div[contains(@class, 'rule') or contains(@class, 'list-item')]//span[contains(text(), '{rule_name}')] | //li[contains(text(), '{rule_name}')]",
                    timeout=10,
                )
                self._safe_click(rule_element)
                time.sleep(1)
            except TimeoutException:
                self.logger.warning(f"Regel '{rule_name}' nicht direkt gefunden")

            # Klicke auf Bearbeiten-Button
            try:
                edit_button = self._wait_and_find(
                    By.XPATH,
                    "//button[contains(text(), 'Bearbeiten')] | //a[contains(text(), 'Bearbeiten')] | //button[contains(@aria-label, 'Bearbeiten')]",
                    timeout=5,
                    clickable=True,
                )
                self._safe_click(edit_button)
                time.sleep(2)
                self.logger.debug("Regel zur Bearbeitung geöffnet")
                return True
            except TimeoutException:
                # Versuche Doppelklick
                try:
                    from selenium.webdriver.common.action_chains import ActionChains

                    rule_element = self._wait_and_find(
                        By.XPATH, f"//*[contains(text(), '{rule_name}')]", timeout=5
                    )
                    ActionChains(self.driver).double_click(rule_element).perform()
                    time.sleep(2)
                    return True
                except Exception:
                    pass

            return False

        except Exception as e:
            self.logger.error(f"Fehler beim Öffnen der Regel: {e}")
            return False

    def _create_new_redirect_field(self) -> bool:
        """
        Erstellt ein neues Umleitungsfeld durch Klicken auf den "Aktion hinzufügen"-Button.

        Returns:
            True wenn ein neues Feld erstellt wurde
        """
        # Verschiedene Selektoren für den "Aktion hinzufügen"-Button ausprobieren
        add_button_selectors = [
            "//button[contains(text(), 'Aktion hinzufügen')]",
            "//a[contains(text(), 'Aktion hinzufügen')]",
            "//button[@data-action='add-action']",
            "//button[contains(text(), 'Add action')]",
            "//a[contains(text(), 'Add action')]",
            "//button[contains(@class, 'add-action')]",
            "//a[contains(@class, 'add-action')]",
            "//*[contains(@class, 'add') and contains(@class, 'action')]",
            "//button[contains(text(), '+')]",
            "//*[@data-action='add']",
        ]

        add_button = None
        for selector in add_button_selectors:
            buttons = self.driver.find_elements(By.XPATH, selector)
            if buttons:
                add_button = buttons[0]
                self.logger.debug(f"'Aktion hinzufügen'-Button gefunden mit Selektor: {selector}")
                break

        if not add_button:
            self.logger.warning("Kein 'Aktion hinzufügen'-Button gefunden")
            return False

        # Button klicken
        self._safe_click(add_button)
        time.sleep(1.5)

        # Versuche "Umleiten nach" als Action auszuwählen
        try:
            # Verschiedene Selektoren für das Dropdown
            dropdown_selectors = [
                'select[name="actioncontent"]',
                ".action-select",
                "select.form-control",
                'select[name*="action"]',
                'select[id*="action"]',
            ]

            action_dropdown = None
            for selector in dropdown_selectors:
                try:
                    action_dropdown = self._wait_and_find(By.CSS_SELECTOR, selector, timeout=3)
                    if action_dropdown:
                        break
                except Exception:
                    continue

            if action_dropdown:
                from selenium.webdriver.support.ui import Select

                select = Select(action_dropdown)

                # Versuche verschiedene Werte für "redirect"
                redirect_values = [
                    "redirect",
                    "Redirect",
                    "umleiten",
                    "Umleiten",
                    "forward",
                    "Forward",
                ]
                for value in redirect_values:
                    try:
                        select.select_by_value(value)
                        self.logger.debug(f"Aktions-Dropdown auf '{value}' gesetzt")
                        break
                    except Exception:
                        continue
        except Exception as e:
            self.logger.debug(f"Konnte Aktions-Dropdown nicht konfigurieren: {e}")

        time.sleep(1)
        return True

    def add_forwarding_address(self, email: str) -> bool:
        """
        Fügt eine Weiterleitungsadresse zur bestehenden Filterregel hinzu.

        Args:
            email: E-Mail-Adresse für die Weiterleitung

        Returns:
            True bei Erfolg
        """
        self.logger.info(f"Füge Weiterleitung hinzu: {email}")

        try:
            # Verschiedene Selektoren für Umleitungs-Input-Felder
            input_selectors = [
                'input[id^="redirect_"]',
                'input[name="to"]',
                'input[name*="redirect"]',
                'input[type="email"]',
                'input[placeholder*="@"]',
                'input[placeholder*="mail"]',
            ]

            def find_empty_redirect_field():
                """Sucht ein leeres Umleitungsfeld."""
                for selector in input_selectors:
                    redirect_inputs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    # Von hinten beginnen (neueste zuerst)
                    for field in reversed(redirect_inputs):
                        try:
                            value = field.get_attribute("value")
                            if not value or value.strip() == "":
                                # Prüfen ob das Feld sichtbar und interaktiv ist
                                if field.is_displayed() and field.is_enabled():
                                    return field
                        except Exception:
                            continue
                return None

            # Erst nach leerem Feld suchen
            empty_field = find_empty_redirect_field()

            # Wenn kein leeres Feld gefunden, erstelle ein neues
            if not empty_field:
                self.logger.debug("Kein leeres Feld gefunden, erstelle neues Umleitungsfeld...")

                if self._create_new_redirect_field():
                    # Nach dem Erstellen erneut nach leerem Feld suchen
                    time.sleep(0.5)
                    empty_field = find_empty_redirect_field()

                    if not empty_field:
                        self.logger.debug(
                            "Suche nach neu erstelltem Feld mit erweiterten Selektoren..."
                        )
                        # Nochmals mit allen Input-Feldern versuchen
                        all_inputs = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            'input[type="text"], input[type="email"], input:not([type])',
                        )
                        for field in reversed(all_inputs):
                            try:
                                value = field.get_attribute("value")
                                field_id = field.get_attribute("id") or ""
                                field_name = field.get_attribute("name") or ""
                                # Prüfen ob es ein Redirect-Feld sein könnte
                                if (
                                    (not value or value.strip() == "")
                                    and field.is_displayed()
                                    and field.is_enabled()
                                ):
                                    if (
                                        "redirect" in field_id.lower()
                                        or "redirect" in field_name.lower()
                                        or "to" in field_name.lower()
                                    ):
                                        empty_field = field
                                        break
                            except Exception:
                                continue

            if empty_field:
                self._safe_send_keys(empty_field, email)
                self.logger.debug(f"E-Mail-Adresse eingegeben: {email}")
                time.sleep(0.3)  # Kurze Pause nach Eingabe
                return True
            else:
                self.logger.warning("Kein leeres Umleitungsfeld gefunden")
                return False

        except Exception as e:
            self.logger.error(f"Fehler beim Hinzufügen der Weiterleitung: {e}")
            return False

    def remove_forwarding_address(self, email: str) -> bool:
        """
        Entfernt eine Weiterleitungsadresse aus der Filterregel.

        Args:
            email: Zu entfernende E-Mail-Adresse

        Returns:
            True bei Erfolg
        """
        self.logger.info(f"Entferne Weiterleitung: {email}")

        try:
            # Find das Input-Feld mit der zu entfernenden Address
            redirect_inputs = self.driver.find_elements(
                By.CSS_SELECTOR, 'input[id^="redirect_"], input[name="to"]'
            )

            target_field = None
            for field in redirect_inputs:
                try:
                    value = field.get_attribute("value")
                    if value and value.lower().strip() == email.lower().strip():
                        target_field = field
                        break
                except Exception:
                    continue

            if not target_field:
                self.logger.warning(f"Weiterleitungsadresse nicht gefunden: {email}")
                return False

            # Find den Entfernen-Button für dieses Field
            # Der Button sollte im selben Container sein (li oder div mit der Action)
            parent = target_field.find_element(
                By.XPATH, "./ancestor::li | ./ancestor::div[contains(@class, 'filter-settings')]"
            )

            try:
                remove_btn = parent.find_element(
                    By.CSS_SELECTOR,
                    'button[data-action="remove-action"], button.remove, button[aria-label*="Entfernen"]',
                )
                self._safe_click(remove_btn)
                self.logger.debug(f"Entfernen-Button geklickt für: {email}")
                time.sleep(0.5)
                return True
            except NoSuchElementException:
                self.logger.warning(f"Entfernen-Button nicht gefunden für: {email}")
                return False

        except Exception as e:
            self.logger.error(f"Fehler beim Entfernen der Weiterleitung: {e}")
            return False

    def save_changes(self) -> bool:
        """
        Speichert die Änderungen an der Filterregel.

        Returns:
            True bei Erfolg
        """
        self.logger.info("Speichere Änderungen...")

        try:
            # OPTIMIERT: Funktionierende Selektoren zuerst, keine Debug-Screenshots
            save_button_selectors = [
                (By.XPATH, "//button[contains(text(), 'Speichern')]"),  # Funktioniert!
                (By.XPATH, "//a[contains(text(), 'Speichern')]"),
                (By.CSS_SELECTOR, 'button[data-action="save"]'),
                (By.CSS_SELECTOR, "button.btn-primary"),
            ]

            save_button = None
            for by, selector in save_button_selectors:
                try:
                    buttons = self.driver.find_elements(by, selector)
                    for btn in buttons:
                        if btn.is_displayed() and btn.is_enabled():
                            save_button = btn
                            self.logger.debug(f"Speichern-Button gefunden mit: {selector}")
                            break
                    if save_button:
                        break
                except Exception:
                    continue

            if save_button:
                self._safe_click(save_button)
                self.logger.debug("Speichern-Button geklickt")
                time.sleep(1.5)
                return True

            self.logger.warning("Speichern-Button nicht gefunden")
            return False

        except Exception as e:
            self.logger.error(f"Fehler beim Speichern: {e}")
            return False

    # ============================================================
    # Methoden für individuelle Regeln (eine Regel pro Mitglied)
    # ============================================================

    def get_managed_emails_from_rules(self) -> Set[str]:
        """
        Liest alle E-Mail-Adressen aus Regeln mit dem konfigurierten Prefix.

        Bei individuellen Regeln hat jede Regel den Namen "{prefix}{email}".

        Returns:
            Set mit E-Mail-Adressen die durch Regeln verwaltet werden
        """
        if not self._logged_in:
            if not self.connect():
                return set()

        emails: Set[str] = set()
        prefix = self.config.rule_prefix
        self.logger.debug(f"Suche nach Regeln mit Prefix: '{prefix}'")

        try:
            if not self._navigate_to_mail_filter():
                self.logger.error("Konnte nicht zu Filterregeln navigieren")
                return set()

            time.sleep(2)

            # Debug: Screenshot der Filterregeln-Seite
            try:
                self.driver.save_screenshot("debug_rules_list.png")
                self.logger.debug("Screenshot der Regelliste gespeichert")
            except Exception:
                pass

            # Versuche verschiedene Selektoren für die Regelliste
            all_found_texts = []

            # Methode 1: CSS Selektoren
            rule_elements = self.driver.find_elements(
                By.CSS_SELECTOR,
                '.rule-list li, .settings-list-view li, [data-type="rule"], .list-item, .listbox li',
            )
            self.logger.debug(f"CSS-Selektoren: {len(rule_elements)} Elemente gefunden")

            for rule_el in rule_elements:
                try:
                    rule_name = rule_el.text.strip()
                    if rule_name:
                        all_found_texts.append(f"CSS: '{rule_name[:50]}...'")
                        # Prüfe ob der Name mit unserem Prefix beginnt
                        if rule_name.startswith(prefix):
                            email = rule_name[len(prefix) :].lower().strip()
                            # Nur erste Zeile (falls mehrzeilig)
                            email = email.split("\n")[0].strip()
                            if "@" in email:
                                emails.add(email)
                                self.logger.debug(f"✓ Regel gefunden: '{rule_name}' -> '{email}'")
                except Exception:
                    continue

            # Methode 2: XPath für Spans/Divs mit dem Prefix
            rule_spans = self.driver.find_elements(
                By.XPATH,
                f"//span[starts-with(text(), '{prefix}')] | //div[starts-with(text(), '{prefix}')] | //*[contains(text(), '{prefix}')]",
            )
            self.logger.debug(f"XPath prefix-Suche: {len(rule_spans)} Elemente gefunden")

            for span in rule_spans:
                try:
                    rule_name = span.text.strip()
                    if rule_name and rule_name.startswith(prefix):
                        all_found_texts.append(f"XPATH: '{rule_name[:50]}...'")
                        email = rule_name[len(prefix) :].lower().strip()
                        email = email.split("\n")[0].strip()
                        if "@" in email:
                            emails.add(email)
                            self.logger.debug(
                                f"✓ Regel gefunden (XPath): '{rule_name}' -> '{email}'"
                            )
                except Exception:
                    continue

            # Methode 3: Alle li-Elemente in der Seite prüfen
            all_li = self.driver.find_elements(By.TAG_NAME, "li")
            self.logger.debug(f"Alle li-Elemente: {len(all_li)} gefunden")
            for li in all_li:
                try:
                    li_text = li.text.strip()
                    if li_text and prefix in li_text:
                        self.logger.debug(f"  li mit Prefix: '{li_text[:80]}...'")
                        # Extrahiere E-Mail wenn möglich
                        if li_text.startswith(prefix):
                            email = li_text[len(prefix) :].lower().strip()
                            email = email.split("\n")[0].strip()
                            if "@" in email:
                                emails.add(email)
                except Exception:
                    continue

            self.logger.info(
                f"{len(emails)} verwaltete E-Mail-Regeln gefunden (Prefix: '{prefix}')"
            )
            if emails:
                self.logger.debug(f"Gefundene E-Mails: {sorted(emails)}")
            else:
                self.logger.warning(f"Keine Regeln mit Prefix '{prefix}' gefunden!")
                self.logger.debug(f"Gefundene Texte (erste 10): {all_found_texts[:10]}")

        except Exception as e:
            self.logger.error(f"Fehler beim Lesen der Regeln: {e}")

        return emails

    def create_individual_rule(self, email: str) -> bool:
        """
        Erstellt eine neue individuelle Filterregel für eine E-Mail-Adresse.

        Die Regel wird mit dem Namen "{prefix}{email}" erstellt und leitet
        alle E-Mails an die angegebene Adresse weiter.

        Args:
            email: E-Mail-Adresse für die Weiterleitung

        Returns:
            True bei Erfolg
        """
        rule_name = f"{self.config.rule_prefix}{email}"
        self.logger.info(f"Erstelle neue Regel: {rule_name}")

        try:
            if not self._navigate_to_mail_filter():
                return False

            time.sleep(2)

            # Debug-Screenshot vor Suche nach "Neue Regel"-Button
            try:
                self.driver.save_screenshot("debug_before_new_rule.png")
            except Exception:
                pass

            # Suche den "Neue Regel erstellen" Button - verschiedene Selektoren
            new_rule_buttons = []
            # OPTIMIERT: Funktionierende Selektoren zuerst
            add_rule_selectors = [
                (By.XPATH, "//button[contains(text(), 'Neue Regel')]"),  # Funktioniert!
                (By.XPATH, "//a[contains(text(), 'Neue Regel')]"),
                (By.CSS_SELECTOR, '[data-action="io.ox/mail/mailfilter/settings/filter/add"]'),
                (By.XPATH, "//button[contains(text(), 'Add new rule')]"),
            ]

            for by, selector in add_rule_selectors:
                try:
                    elements = self.driver.find_elements(by, selector)
                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            new_rule_buttons = [elem]
                            self.logger.debug(f"'Neue Regel'-Button gefunden mit: {selector}")
                            break
                    if new_rule_buttons:
                        break
                except Exception:
                    continue

            if not new_rule_buttons:
                self.logger.error("Konnte 'Neue Regel erstellen'-Button nicht finden")
                # Debug-Screenshot
                try:
                    self.driver.save_screenshot("debug_no_add_button.png")
                    with open("debug_no_add_button.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                except Exception:
                    pass
                return False

            self._safe_click(new_rule_buttons[0])
            time.sleep(2)  # Zeit für das Modal

            # Jetzt sind wir im Regel-Bearbeitungsdialog
            # 1. Regelnamen setzen - OPTIMIERT: Funktionierende Selektoren zuerst
            name_input = None
            name_selectors = [
                (By.CSS_SELECTOR, 'input[name="rulename"]'),  # Funktioniert!
                (By.XPATH, "//input[@name='rulename']"),
                (By.CSS_SELECTOR, 'input[id*="rulename"]'),
            ]

            for by, selector in name_selectors:
                try:
                    elements = self.driver.find_elements(by, selector)
                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            name_input = elem
                            self.logger.debug(f"Namensfeld gefunden mit Selektor: {selector}")
                            break
                    if name_input:
                        break
                except Exception:
                    continue

            if not name_input:
                self.logger.error("Kein Namensfeld gefunden - prüfe debug_new_rule_dialog.png/html")
                # Liste alle sichtbaren Input-Felder auf
                all_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input")
                self.logger.debug(f"Gefundene Input-Felder: {len(all_inputs)}")
                for i, inp in enumerate(all_inputs[:10]):
                    try:
                        self.logger.debug(
                            f"  Input {i}: type={inp.get_attribute('type')}, "
                            f"name={inp.get_attribute('name')}, "
                            f"id={inp.get_attribute('id')}, "
                            f"visible={inp.is_displayed()}"
                        )
                    except Exception:
                        pass
                return False

            try:
                name_input.clear()
                self._safe_send_keys(name_input, rule_name)
                self.logger.debug(f"Regelname gesetzt: {rule_name}")
            except Exception as e:
                self.logger.error(f"Konnte Regelnamen nicht setzen: {e}")
                return False

            time.sleep(0.5)

            # 2. Aktion hinzufügen: Umleiten
            if not self._add_redirect_action_to_new_rule(email):
                self.logger.error("Konnte Umleitungsaktion nicht hinzufügen")
                return False

            # 3. Speichern
            time.sleep(1)
            if self.save_changes():
                self.logger.info(f"✅ Regel erstellt: {rule_name}")
                return True
            else:
                self.logger.error("Konnte Regel nicht speichern")
                return False

        except Exception as e:
            self.logger.error(f"Fehler beim Erstellen der Regel: {e}")
            return False

    def _add_redirect_action_to_new_rule(self, email: str) -> bool:
        """
        Fügt eine Umleitungsaktion zu einer neuen Regel hinzu.
        OPTIMIERT: Funktionierende Selektoren priorisiert, kürzere Wartezeiten.
        """
        try:
            # Finde den Aktionen-Bereich (legend.actions -> parent fieldset)
            actions_fieldset = None
            for by, selector in [
                (By.XPATH, "//legend[contains(@class, 'actions')]/parent::fieldset"),
                (By.XPATH, "//legend[contains(text(), 'Aktion')]/parent::fieldset"),
            ]:
                try:
                    elements = self.driver.find_elements(by, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            actions_fieldset = elem
                            break
                    if actions_fieldset:
                        break
                except Exception:
                    continue

            # Klicke "Aktion hinzufügen"
            add_action_clicked = False
            if actions_fieldset:
                try:
                    for link in actions_fieldset.find_elements(By.TAG_NAME, "a"):
                        link_text = link.text.strip().lower()
                        if "aktion" in link_text and "hinzufügen" in link_text:
                            if link.is_displayed() and link.is_enabled():
                                self._safe_click(link)
                                self.logger.debug("'Aktion hinzufügen' geklickt")
                                add_action_clicked = True
                                time.sleep(1)
                                break
                except Exception:
                    pass

            if not add_action_clicked:
                # Fallback: Suche global
                for link in self.driver.find_elements(
                    By.XPATH, "//a[contains(text(), 'Aktion hinzufügen')]"
                ):
                    if link.is_displayed() and link.is_enabled():
                        self._safe_click(link)
                        add_action_clicked = True
                        time.sleep(1)
                        break

            if not add_action_clicked:
                self.logger.warning("Kein 'Aktion hinzufügen'-Button gefunden")
                return False

            # Aktualisiere Aktionen-Bereich nach Klick
            actions_fieldset = None
            for by, selector in [
                (By.XPATH, "//legend[contains(@class, 'actions')]/parent::fieldset"),
                (By.XPATH, "//legend[contains(text(), 'Aktion')]/parent::fieldset"),
            ]:
                try:
                    elements = self.driver.find_elements(by, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            actions_fieldset = elem
                            break
                    if actions_fieldset:
                        break
                except Exception:
                    continue

            # Öffne Dropdown-Toggle im Aktionen-Bereich
            dropdown_opened = False
            if actions_fieldset:
                try:
                    for toggle in actions_fieldset.find_elements(
                        By.CSS_SELECTOR, ".dropdown-toggle"
                    ):
                        if toggle.is_displayed() and toggle.is_enabled():
                            self._safe_click(toggle)
                            dropdown_opened = True
                            time.sleep(0.5)
                            break
                except Exception:
                    pass

            # Wähle "Umleiten nach" aus dem Dropdown
            redirect_selected = False
            for by, selector in [
                (By.CSS_SELECTOR, 'a[data-value="redirect"]'),
                (By.XPATH, "//a[contains(text(), 'Umleiten nach')]"),
            ]:
                try:
                    for item in self.driver.find_elements(by, selector):
                        if item.is_displayed():
                            self._safe_click(item)
                            self.logger.debug("'Umleiten nach' ausgewählt")
                            redirect_selected = True
                            time.sleep(1)
                            break
                    if redirect_selected:
                        break
                except Exception:
                    continue

            if not redirect_selected:
                self.logger.warning("Konnte 'Umleiten nach' nicht auswählen")
                self.logger.warning(
                    "⚠️  Möglicherweise wurde das Strato-Limit von 50 Weiterleitungsregeln erreicht!"
                )
                return False

            # Finde E-Mail-Eingabefeld
            for by, selector in [
                (By.CSS_SELECTOR, 'input[id^="redirect_"]'),
                (By.CSS_SELECTOR, 'input[id^="redirect"]'),
                (By.CSS_SELECTOR, 'li.action input[type="text"]'),
            ]:
                try:
                    for field in reversed(self.driver.find_elements(by, selector)):
                        value = field.get_attribute("value") or ""
                        if not value.strip() and field.is_displayed() and field.is_enabled():
                            self._safe_send_keys(field, email)
                            self.logger.debug(f"Umleitungsadresse eingegeben: {email}")
                            return True
                except Exception:
                    continue

            self.logger.warning("Kein E-Mail-Feld gefunden")
            return False

        except Exception as e:
            self.logger.error(f"Fehler beim Hinzufügen der Umleitungsaktion: {e}")
            return False

    def delete_individual_rule(self, email: str) -> bool:
        """
        Löscht die individuelle Filterregel für eine E-Mail-Adresse.
            email: E-Mail-Adresse deren Regel gelöscht werden soll

        Returns:
            True bei Erfolg
        """
        rule_name = f"{self.config.rule_prefix}{email}"
        self.logger.info(f"Lösche Regel: {rule_name}")

        try:
            if not self._navigate_to_mail_filter():
                return False

            time.sleep(2)

            # Finde die Regel in der Liste
            rule_element = None

            # Versuche verschiedene Selektoren
            selectors = [
                f"//li[contains(text(), '{rule_name}')]",
                f"//span[contains(text(), '{rule_name}')]/ancestor::li",
                f"//div[contains(text(), '{rule_name}')]/ancestor::li",
                f"//*[contains(text(), '{rule_name}')]",
            ]

            for selector in selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                if elements:
                    rule_element = elements[0]
                    break

            if not rule_element:
                self.logger.warning(f"Regel '{rule_name}' nicht gefunden")
                return False

            # Klicke auf die Regel um sie auszuwählen
            self._safe_click(rule_element)
            time.sleep(1)

            # Suche den Löschen-Button
            delete_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Löschen')] | "
                "//a[contains(text(), 'Löschen')] | "
                "//button[contains(text(), 'Delete')] | "
                "//button[contains(text(), 'Entfernen')] | "
                "//button[@data-action='delete'] | "
                "//button[@aria-label='Löschen'] | "
                "//button[contains(@class, 'delete')]",
            )

            if not delete_buttons:
                # Versuche Kontextmenü
                try:
                    from selenium.webdriver.common.action_chains import ActionChains

                    ActionChains(self.driver).context_click(rule_element).perform()
                    time.sleep(0.5)

                    delete_menu = self.driver.find_elements(
                        By.XPATH,
                        "//a[contains(text(), 'Löschen')] | //li[contains(text(), 'Löschen')]",
                    )
                    if delete_menu:
                        self._safe_click(delete_menu[0])
                        time.sleep(1)
                        self.logger.info(f"✅ Regel gelöscht: {rule_name}")
                        return True
                except Exception:
                    pass

                self.logger.error(f"Konnte Löschen-Button für '{rule_name}' nicht finden")
                return False

            self._safe_click(delete_buttons[0])
            time.sleep(1)

            # Bestätige evtl. Bestätigungsdialog
            try:
                confirm_buttons = self.driver.find_elements(
                    By.XPATH,
                    "//button[contains(text(), 'OK')] | "
                    "//button[contains(text(), 'Ja')] | "
                    "//button[contains(text(), 'Bestätigen')] | "
                    "//button[contains(text(), 'Delete')]",
                )
                if confirm_buttons:
                    self._safe_click(confirm_buttons[0])
                    time.sleep(1)
            except Exception:
                pass

            self.logger.info(f"✅ Regel gelöscht: {rule_name}")
            return True

        except Exception as e:
            self.logger.error(f"Fehler beim Löschen der Regel: {e}")
            return False

    def disconnect(self):
        """Beendet den Browser und die Session."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self._logged_in = False
        self.logger.debug("Browser geschlossen")

    def take_screenshot(self, filename: str = "screenshot.png"):
        """Erstellt einen Screenshot (für Debugging)."""
        if self.driver:
            self.driver.save_screenshot(filename)
            self.logger.info(f"Screenshot gespeichert: {filename}")

    def test_connection(self) -> bool:
        """
        Testet die Verbindung zum Strato Webmail.

        Returns:
            True wenn Login erfolgreich
        """
        try:
            success = self.connect()
            if success:
                self.logger.info("✅ Strato Webmail: Verbindung OK")
            return success
        finally:
            self.disconnect()

    def __enter__(self):
        """Context Manager Support."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager Support."""
        self.disconnect()
        return False
