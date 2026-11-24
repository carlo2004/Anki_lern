# Variator – Einstellungen

Die normalen Einstellungen sind unter **Variator → Einstellungen…** erreichbar.
Anbieter, Modell und API-Schlüssel werden unter **Variator → Verbindung
einrichten oder ändern…** festgelegt. Erweiterte Rohwerte können unter
**Werkzeuge → Erweiterungen → Variator → Konfiguration** eingesehen werden.

## Lernen

- `ui_language`: Sprache der Variator-Oberfläche. `auto` folgt Ankis aktiver
  Oberflächensprache; außerdem sind `de`, `en`, `es`, `fr` und `ru` wählbar.
  Nicht unterstützte Anki-Sprachen fallen auf Englisch zurück. Die erzeugte
  Kartenfrage bleibt unabhängig davon in der Sprache der Originalkarte.
- `enabled`: Zeigt verfügbare Fragevarianten beim Lernen an.
- `show_original_on_answer`: Zeigt die Originalfrage nach dem Aufdecken direkt
  unter der neuen Frage an (Standard: aktiviert). Bei deaktiviertem Wert folgt
  die Lösung unmittelbar auf die neue Frage.
- `rewrite_intensity`: Stärke der Umformulierung. Erlaubt sind `near` (nah am
  Original), `light` (leicht verändert), `distinct` (deutlich anders, Standard)
  und `maximum` (maximal anders). Ungültige oder ältere Werte fallen auf
  `distinct` zurück.
- `variant_count`: Kompatibilitätswert. Variator erzeugt immer genau eine
  Variante pro Karte.
- `sent_card_count`: Lokaler Gesamtzähler der Karten, für die eine KI-Anfrage
  gestartet wurde. Automatische HTTP-Wiederholungen zählen nicht erneut; der
  Zähler enthält keine Karteninhalte.

## Automatische Vorbereitung

- `live_prefetch_enabled`: Aktiviert oder pausiert automatische Anfragen. Nur
  bei aktivem Wert, gültiger Zustimmung und verfügbarem API-Schlüssel bereitet
  Variator beim Profilstart im Leerlauf je eine tatsächlich anstehende Karte
  pro normalem Deck vor (aktuelles Deck zuerst). Beim Öffnen eines Decks hat
  dessen erste anstehende Karte Vorrang; während des Lernens folgt der rollende
  Vorlauf. Eltern-/Unterdeck-Dopplungen und bereits vorbereitete Karten
  verursachen keine zweite Anbieteranfrage.
  Der Zustand ist jederzeit direkt im oberen Menü als **Variator Ein**,
  **Variator Aus** oder **Variator Fehler** sichtbar. Der native Menüpunkt
  **Automatische Fragen** schaltet die Funktion um.
- `live_prefetch_count`: Größe des rollenden Vorlaufs (1–10, Standard 3).
- `live_consent_revoked_profiles`: Interne, profilgetrennte Sperrliste nach
  einem ausdrücklichen Widerruf. Sie verhindert die Wiederverwendung alter
  Zustimmungsdaten, wenn deren Datei nicht gelöscht werden konnte.

## Offline-Vorbereitung

- `offline_prepare_count`: Zuletzt gewählte Anzahl für **Deck für offline
  vorbereiten…** (1–50, Standard 20). Die vorbereiteten Varianten liegen nur
  im lokalen Anki-Profil dieses Computers und werden nicht über Anki Sync oder
  an mobile Anki-Apps übertragen. Jede neu erzeugte Variante kann API-Kosten
  verursachen.

## Verbindung und erweiterte Werte

- `provider`: Zuletzt verwendeter Anbieter (`openai`, `gemini`, `anthropic`
  oder `xai`).
- `model`: Zuletzt verwendete Modellkennung; das Feld ist frei editierbar.
- `timeout_seconds`: Maximale Wartezeit pro API-Anfrage (5–3600 Sekunden,
  Standard 90).
- `max_retries`: Wiederholungen für eindeutige temporäre Server- und
  Ratenlimitfehler (0–5, Standard 2).

API-Schlüssel werden nicht in `config.json` gespeichert. Variator liest zuerst
die passende Umgebungsvariable (`OPENAI_API_KEY`, `GEMINI_API_KEY`,
`ANTHROPIC_API_KEY` oder `XAI_API_KEY`). Ohne **API-Schlüssel merken** gilt eine
Eingabe nur bis zum Schließen von Anki. Mit der Option wird sie im lokalen
Profil dieses Geräts gespeichert und nicht über Anki Sync übertragen.

Unter Windows werden gemerkte Schlüssel mit DPAPI für das aktuelle
Windows-Konto geschützt. Beim Lesen eines bestehenden Klartextspeichers aus
Variator 0.4.x migriert Variator ihn automatisch. Auf macOS und Linux ist die
lokale Profildatei der transparente Fallback; dort kann sie von Programmen mit
Profilzugriff gelesen werden.
