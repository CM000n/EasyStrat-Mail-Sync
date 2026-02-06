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
    rule_name: str = "Maennerchor"  # Name der Filterregel für Weiterleitungen


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
            # Stelle sicher, dass wir im Bearbeitungsdialog sind
            # Suche den "Action hinzufügen"-Button
            add_action_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Aktion hinzufügen')] | //a[contains(text(), 'Aktion hinzufügen')] | //button[@data-action='add-action']",
            )

            if add_action_buttons:
                self._safe_click(add_action_buttons[0])
                time.sleep(1)

                # Wähle "Umleiten nach" also Action
                try:
                    # Öffne das Dropdown für die Action
                    action_dropdown = self._wait_and_find(
                        By.CSS_SELECTOR,
                        'select[name="actioncontent"], .action-select, select.form-control',
                        timeout=5,
                    )
                    # Wähle "redirect" Option
                    from selenium.webdriver.support.ui import Select

                    Select(action_dropdown).select_by_value("redirect")
                except Exception:
                    self.logger.debug("Konnte Aktions-Dropdown nicht finden")

                time.sleep(1)

            # Find ein leeres Umleitungs-Input-Feld oder das zuletzt hinzugefügte
            redirect_inputs = self.driver.find_elements(
                By.CSS_SELECTOR, 'input[id^="redirect_"], input[name="to"]'
            )

            # Find ein leeres Field
            empty_field = None
            for field in reversed(redirect_inputs):  # Von hinten beginnen (neueste zuerst)
                try:
                    if not field.get_attribute("value"):
                        empty_field = field
                        break
                except Exception:
                    continue

            if empty_field:
                self._safe_send_keys(empty_field, email)
                self.logger.debug(f"E-Mail-Adresse eingegeben: {email}")
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
            # Suche den Speichern-Button
            save_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Speichern')] | //button[contains(text(), 'Save')] | //button[@data-action='save']",
            )

            if save_buttons:
                for btn in save_buttons:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            self._safe_click(btn)
                            self.logger.debug("Speichern-Button geklickt")
                            time.sleep(2)
                            return True
                    except Exception:
                        continue

            # Alternative: Submit per Enter im aktiven Element
            from selenium.webdriver.common.keys import Keys

            active = self.driver.switch_to.active_element
            active.send_keys(Keys.ENTER)
            time.sleep(1)

            self.logger.warning("Speichern-Button nicht gefunden oder nicht klickbar")
            return False

        except Exception as e:
            self.logger.error(f"Fehler beim Speichern: {e}")
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
