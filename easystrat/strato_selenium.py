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
                '.action-select',
                'select.form-control',
                'select[name*="action"]',
                'select[id*="action"]',
            ]
            
            action_dropdown = None
            for selector in dropdown_selectors:
                try:
                    action_dropdown = self._wait_and_find(
                        By.CSS_SELECTOR, selector, timeout=3
                    )
                    if action_dropdown:
                        break
                except Exception:
                    continue
            
            if action_dropdown:
                from selenium.webdriver.support.ui import Select
                select = Select(action_dropdown)
                
                # Versuche verschiedene Werte für "redirect"
                redirect_values = ["redirect", "Redirect", "umleiten", "Umleiten", "forward", "Forward"]
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
                        self.logger.debug("Suche nach neu erstelltem Feld mit erweiterten Selektoren...")
                        # Nochmals mit allen Input-Feldern versuchen
                        all_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], input[type="email"], input:not([type])')
                        for field in reversed(all_inputs):
                            try:
                                value = field.get_attribute("value")
                                field_id = field.get_attribute("id") or ""
                                field_name = field.get_attribute("name") or ""
                                # Prüfen ob es ein Redirect-Feld sein könnte
                                if (not value or value.strip() == "") and field.is_displayed() and field.is_enabled():
                                    if "redirect" in field_id.lower() or "redirect" in field_name.lower() or "to" in field_name.lower():
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

        try:
            if not self._navigate_to_mail_filter():
                self.logger.error("Konnte nicht zu Filterregeln navigieren")
                return set()

            time.sleep(2)

            # Alle Regelnamen sammeln
            rule_elements = self.driver.find_elements(
                By.CSS_SELECTOR,
                '.rule-list li, .settings-list-view li, [data-type="rule"], .list-item'
            )
            
            self.logger.debug(f"{len(rule_elements)} Regel-Elemente gefunden")

            for rule_el in rule_elements:
                try:
                    # Versuche den Regelnamen zu extrahieren
                    rule_name = rule_el.text.strip()
                    
                    # Prüfe ob der Name mit unserem Prefix beginnt
                    if rule_name.startswith(prefix):
                        # Email aus dem Regelnamen extrahieren
                        email = rule_name[len(prefix):].lower().strip()
                        if "@" in email:
                            emails.add(email)
                            self.logger.debug(f"Verwaltete Regel gefunden: {rule_name} -> {email}")
                except Exception:
                    continue

            # Alternative: Auch nach span-Elementen suchen
            rule_spans = self.driver.find_elements(
                By.XPATH,
                f"//span[starts-with(text(), '{prefix}')] | //div[starts-with(text(), '{prefix}')]"
            )
            
            for span in rule_spans:
                try:
                    rule_name = span.text.strip()
                    if rule_name.startswith(prefix):
                        email = rule_name[len(prefix):].lower().strip()
                        if "@" in email:
                            emails.add(email)
                except Exception:
                    continue

            self.logger.info(f"{len(emails)} verwaltete E-Mail-Regeln gefunden (Prefix: {prefix})")

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
            add_rule_selectors = [
                # XPath für deutsche UI
                (By.XPATH, "//button[contains(text(), 'Neue Regel')]"),
                (By.XPATH, "//a[contains(text(), 'Neue Regel')]"),
                (By.XPATH, "//button[contains(text(), 'Regel hinzufügen')]"),
                (By.XPATH, "//a[contains(text(), 'Regel hinzufügen')]"),
                (By.XPATH, "//button[contains(text(), 'Hinzufügen')]"),
                (By.XPATH, "//a[contains(text(), 'Hinzufügen')]"),
                # XPath für englische UI
                (By.XPATH, "//button[contains(text(), 'Add new rule')]"),
                (By.XPATH, "//a[contains(text(), 'Add new rule')]"),
                (By.XPATH, "//button[contains(text(), 'Add rule')]"),
                (By.XPATH, "//button[contains(text(), 'New rule')]"),
                # Data-Attribute
                (By.XPATH, "//button[@data-action='create']"),
                (By.XPATH, "//a[@data-action='create']"),
                (By.XPATH, "//*[@data-action='io.ox/mail/mailfilter/settings/filter/add']"),
                # CSS Selektoren
                (By.CSS_SELECTOR, 'button.add-rule'),
                (By.CSS_SELECTOR, 'a.add-rule'),
                (By.CSS_SELECTOR, '.btn-add-rule'),
                (By.CSS_SELECTOR, '[data-action="io.ox/mail/mailfilter/settings/filter/add"]'),
                (By.CSS_SELECTOR, 'button.btn-primary'),  # Oft ist der Haupt-Button primär
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
            time.sleep(3)  # Mehr Zeit für das Modal

            # Debug-Screenshot nach Klick auf "Neue Regel"
            try:
                self.driver.save_screenshot("debug_new_rule_dialog.png")
                with open("debug_new_rule_dialog.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                self.logger.debug("Debug-Dateien für neuen Regel-Dialog gespeichert")
            except Exception:
                pass

            # Jetzt sind wir im Regel-Bearbeitungsdialog
            # 1. Regelnamen setzen - verschiedene Selektoren ausprobieren
            name_input = None
            name_selectors = [
                # CSS Selektoren
                (By.CSS_SELECTOR, 'input[name="rulename"]'),
                (By.CSS_SELECTOR, 'input[id*="rulename"]'),
                (By.CSS_SELECTOR, 'input[placeholder*="Name"]'),
                (By.CSS_SELECTOR, 'input.rule-name'),
                (By.CSS_SELECTOR, '.modal input[type="text"]:first-of-type'),
                (By.CSS_SELECTOR, '.io-ox-mailfilter-edit input[type="text"]'),
                (By.CSS_SELECTOR, 'input.form-control[type="text"]'),
                (By.CSS_SELECTOR, '.settings-detail-pane input[type="text"]'),
                # XPath Selektoren
                (By.XPATH, "//input[@name='rulename']"),
                (By.XPATH, "//label[contains(text(), 'Name')]/following::input[1]"),
                (By.XPATH, "//label[contains(text(), 'Regelname')]/following::input[1]"),
                (By.XPATH, "//div[contains(@class, 'modal')]//input[@type='text'][1]"),
                (By.XPATH, "//input[contains(@class, 'form-control')][@type='text']"),
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
                all_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input')
                self.logger.debug(f"Gefundene Input-Felder: {len(all_inputs)}")
                for i, inp in enumerate(all_inputs[:10]):
                    try:
                        self.logger.debug(f"  Input {i}: type={inp.get_attribute('type')}, "
                                        f"name={inp.get_attribute('name')}, "
                                        f"id={inp.get_attribute('id')}, "
                                        f"visible={inp.is_displayed()}")
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

            time.sleep(1)

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
        
        Args:
            email: Ziel-E-Mail-Adresse für die Umleitung
            
        Returns:
            True bei Erfolg
        """
        try:
            # Debug-Screenshot vor dem Hinzufügen der Aktion
            try:
                self.driver.save_screenshot("debug_before_add_action.png")
                with open("debug_before_add_action.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                self.logger.debug("Debug-Dateien vor Aktion hinzufügen gespeichert")
            except Exception:
                pass

            # Suche den "Aktion hinzufügen"-Button mit verschiedenen Selektoren
            add_action_selectors = [
                (By.XPATH, "//button[contains(text(), 'Aktion hinzufügen')]"),
                (By.XPATH, "//a[contains(text(), 'Aktion hinzufügen')]"),
                (By.XPATH, "//button[contains(text(), 'Add action')]"),
                (By.XPATH, "//a[contains(text(), 'Add action')]"),
                (By.XPATH, "//button[@data-action='add-action']"),
                (By.XPATH, "//*[contains(@class, 'add-action')]"),
                (By.CSS_SELECTOR, 'button.add-action'),
                (By.CSS_SELECTOR, 'a.add-action'),
                (By.CSS_SELECTOR, '[data-action="add-action"]'),
                # Open-Xchange spezifisch
                (By.CSS_SELECTOR, '.actions .dropdown-toggle'),
                (By.CSS_SELECTOR, 'fieldset.actions button'),
                (By.XPATH, "//fieldset[contains(@class, 'actions')]//button"),
            ]
            
            add_action_clicked = False
            for by, selector in add_action_selectors:
                try:
                    elements = self.driver.find_elements(by, selector)
                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            self._safe_click(elem)
                            self.logger.debug(f"'Aktion hinzufügen'-Button geklickt: {selector}")
                            add_action_clicked = True
                            time.sleep(1.5)
                            break
                    if add_action_clicked:
                        break
                except Exception:
                    continue
            
            if not add_action_clicked:
                self.logger.debug("Kein 'Aktion hinzufügen'-Button gefunden - vielleicht bereits eine Aktion vorhanden")

            # Wähle "Umleiten nach" im Aktions-Dropdown
            # Suche alle Select-Elemente und versuche "redirect" auszuwählen
            action_dropdown_selectors = [
                (By.CSS_SELECTOR, 'select[name*="action"]'),
                (By.CSS_SELECTOR, 'select.action-select'),
                (By.CSS_SELECTOR, 'select.form-control'),
                (By.CSS_SELECTOR, '.actions select'),
                (By.CSS_SELECTOR, 'fieldset.actions select'),
                (By.XPATH, "//select[contains(@name, 'action')]"),
                (By.XPATH, "//fieldset[contains(@class, 'actions')]//select"),
            ]
            
            redirect_selected = False
            from selenium.webdriver.support.ui import Select
            
            for by, selector in action_dropdown_selectors:
                if redirect_selected:
                    break
                try:
                    dropdowns = self.driver.find_elements(by, selector)
                    for dropdown in dropdowns:
                        if not dropdown.is_displayed():
                            continue
                        try:
                            select = Select(dropdown)
                            # Versuche verschiedene Werte für "redirect"
                            redirect_options = [
                                "redirect", "Redirect", "umleiten", "Umleiten", 
                                "Umleiten an", "forward", "Forward", 
                                "Weiterleiten", "weiterleiten"
                            ]
                            
                            # Erst nach Value versuchen
                            for value in redirect_options:
                                try:
                                    select.select_by_value(value)
                                    self.logger.debug(f"Aktion auf '{value}' gesetzt (by value)")
                                    redirect_selected = True
                                    break
                                except Exception:
                                    pass
                            
                            # Dann nach sichtbarem Text
                            if not redirect_selected:
                                for text in redirect_options:
                                    try:
                                        select.select_by_visible_text(text)
                                        self.logger.debug(f"Aktion auf '{text}' gesetzt (by text)")
                                        redirect_selected = True
                                        break
                                    except Exception:
                                        pass
                            
                            # Als letztes: Suche in allen Optionen
                            if not redirect_selected:
                                for option in select.options:
                                    opt_text = option.text.lower()
                                    opt_value = option.get_attribute("value").lower()
                                    if "redirect" in opt_text or "umleit" in opt_text or "weiterleit" in opt_text:
                                        select.select_by_visible_text(option.text)
                                        self.logger.debug(f"Aktion gefunden und gesetzt: {option.text}")
                                        redirect_selected = True
                                        break
                                    elif "redirect" in opt_value or "umleit" in opt_value:
                                        select.select_by_value(option.get_attribute("value"))
                                        self.logger.debug(f"Aktion gefunden (value): {opt_value}")
                                        redirect_selected = True
                                        break
                            
                            if redirect_selected:
                                break
                        except Exception as e:
                            self.logger.debug(f"Dropdown-Fehler: {e}")
                            continue
                except Exception:
                    continue
            
            if not redirect_selected:
                self.logger.warning("Konnte 'Umleiten'-Aktion nicht auswählen")
                # Debug: Liste alle Dropdowns auf
                all_selects = self.driver.find_elements(By.CSS_SELECTOR, 'select')
                self.logger.debug(f"Gefundene Select-Elemente: {len(all_selects)}")
                for i, sel in enumerate(all_selects[:5]):
                    try:
                        self.logger.debug(f"  Select {i}: name={sel.get_attribute('name')}, visible={sel.is_displayed()}")
                    except Exception:
                        pass

            time.sleep(1.5)

            # Debug-Screenshot nach Auswahl der Aktion
            try:
                self.driver.save_screenshot("debug_after_action_select.png")
            except Exception:
                pass

            # Finde das E-Mail-Eingabefeld für die Umleitung
            # Erweiterte Selektoren für das Eingabefeld
            redirect_input_selectors = [
                (By.CSS_SELECTOR, 'input[id^="redirect_"]'),
                (By.CSS_SELECTOR, 'input[name="to"]'),
                (By.CSS_SELECTOR, 'input[type="email"]'),
                (By.CSS_SELECTOR, 'input[placeholder*="@"]'),
                (By.CSS_SELECTOR, 'input[placeholder*="mail"]'),
                (By.CSS_SELECTOR, 'input[placeholder*="Mail"]'),
                (By.CSS_SELECTOR, 'input[name*="redirect"]'),
                (By.CSS_SELECTOR, '.actions input[type="text"]'),
                (By.CSS_SELECTOR, 'fieldset.actions input[type="text"]'),
                (By.CSS_SELECTOR, 'fieldset.actions input'),
                (By.XPATH, "//fieldset[contains(@class, 'actions')]//input[@type='text']"),
                (By.XPATH, "//input[contains(@placeholder, 'mail') or contains(@placeholder, 'Mail')]"),
            ]
            
            email_field = None
            for by, selector in redirect_input_selectors:
                try:
                    fields = self.driver.find_elements(by, selector)
                    for field in reversed(fields):  # Von hinten (neueste zuerst)
                        try:
                            value = field.get_attribute("value")
                            if (not value or value.strip() == "") and field.is_displayed() and field.is_enabled():
                                email_field = field
                                self.logger.debug(f"E-Mail-Feld gefunden mit: {selector}")
                                break
                        except Exception:
                            continue
                    if email_field:
                        break
                except Exception:
                    continue

            if email_field:
                self._safe_send_keys(email_field, email)
                self.logger.debug(f"Umleitungsadresse eingegeben: {email}")
                return True
            
            # Fallback: Versuche alle sichtbaren Text-Inputs
            self.logger.debug("Versuche Fallback: Alle sichtbaren Text-Inputs durchsuchen")
            all_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], input:not([type])')
            for field in reversed(all_inputs):
                try:
                    value = field.get_attribute("value")
                    if (not value or value.strip() == "") and field.is_displayed() and field.is_enabled():
                        # Prüfe ob es NICHT das Namensfeld ist
                        field_name = field.get_attribute("name") or ""
                        field_id = field.get_attribute("id") or ""
                        if "name" not in field_name.lower() and "rulename" not in field_id.lower():
                            self._safe_send_keys(field, email)
                            self.logger.debug(f"Umleitungsadresse eingegeben (Fallback): {email}")
                            return True
                except Exception:
                    continue

            self.logger.warning("Kein leeres Umleitungsfeld gefunden")
            # Debug: Liste alle Input-Felder
            self.logger.debug(f"Alle Input-Felder: {len(all_inputs)}")
            for i, inp in enumerate(all_inputs[:10]):
                try:
                    self.logger.debug(f"  Input {i}: type={inp.get_attribute('type')}, "
                                    f"name={inp.get_attribute('name')}, "
                                    f"value='{inp.get_attribute('value')}', "
                                    f"visible={inp.is_displayed()}")
                except Exception:
                    pass
            return False

        except Exception as e:
            self.logger.error(f"Fehler beim Hinzufügen der Umleitungsaktion: {e}")
            return False

    def delete_individual_rule(self, email: str) -> bool:
        """
        Löscht die individuelle Filterregel für eine E-Mail-Adresse.
        
        Args:
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
                "//button[contains(@class, 'delete')]"
            )

            if not delete_buttons:
                # Versuche Kontextmenü
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).context_click(rule_element).perform()
                    time.sleep(0.5)
                    
                    delete_menu = self.driver.find_elements(
                        By.XPATH, "//a[contains(text(), 'Löschen')] | //li[contains(text(), 'Löschen')]"
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
                    "//button[contains(text(), 'Delete')]"
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
