# Variator

**Neue Fragen. Weniger Wiedererkennung. Mehr aktives Abrufen.**

Variator formuliert die Vorderseite einer anstehenden Anki-Karte neu, mit dem
Ziel, den abgefragten Wissenskern zu erhalten. Dadurch reicht es nicht mehr, eine Karte
an ihrem vertrauten Satzbild zu erkennen. Notizfelder, Kartenvorlagen, Antwort,
Lernverlauf und Ankis Zeitplanung bleiben unverändert.

Pro Karte wird genau eine neue Frage erzeugt. Wenn keine geprüfte Variante
bereitsteht, erscheint ohne Wartezeit die Originalkarte. Die Originalfrage kann
während des Lernens jederzeit über Ankis untere Leiste angezeigt werden. Nach
dem Aufdecken steht sie standardmäßig direkt unter der neuen Frage, damit beide
Formulierungen leicht vergleichbar sind; dies lässt sich in den Einstellungen
ausblenden.

## Installation

1. `Variator-0.5.15.ankiaddon` öffnen oder in Anki über **Werkzeuge →
   Erweiterungen → Aus Datei installieren** auswählen.
2. Anki neu starten.
3. Im oberen Menü **Variator → Verbindung einrichten oder ändern…** öffnen,
   Anbieter und API-Schlüssel angeben und die Übertragung bestätigen.

Variator benötigt Anki Desktop 24.11 oder neuer und keine zusätzlich
installierten Python-Pakete. Die aktuelle Version wurde mit Anki 26.09.4 geprüft.

## Sprache

Variator folgt standardmäßig automatisch Ankis Oberflächensprache. Unterstützt
werden Deutsch, Englisch, Spanisch, Französisch und Russisch. Unter **Variator
→ Einstellungen…** kann die Sprache auch fest gewählt werden.

Die Sprache der Oberfläche beeinflusst die Karten nicht: Eine neu formulierte
Frage bleibt immer in der Sprache der Originalkarte.

## Lernen ohne Wartezeit

Sobald **Variator → Automatische Fragen** aktiv ist und eine verwendbare
Verbindung besteht, bereitet Variator im Hintergrund vor:

- beim Öffnen des Profils je eine tatsächlich anstehende Karte pro Deck, wobei
  das aktuell gewählte Deck zuerst kommt;
- beim Öffnen eines Decks dessen erste tatsächlich anstehende Karte mit
  Vorrang;
- während des Lernens einen rollenden Vorlauf der nächsten Karten, standardmäßig
  drei.

Damit ist bereits die erste Frage eines geöffneten Decks nach Möglichkeit neu
formuliert. Mehrfach ausgelöste Vorbereitungen derselben Karte – auch über
Eltern- und Unterdecks – werden zusammengeführt. Vorhandene Ergebnisse werden
wiederverwendet, und die Deckreserve arbeitet einzeln nur im Leerlauf. Leere
Decks und Karten, die Variator aus Sicherheitsgründen nicht unterstützt,
werden übersprungen. Die Deckauswahl und der Zustand von Ankis Scheduler werden
durch die Hintergrundvorbereitung nicht verändert.

Der Vorlauf lässt sich unter **Variator → Einstellungen…** zwischen 1 und 10
Karten einstellen oder vollständig pausieren. Eine bereits sichtbare Frage wird
niemals nachträglich ausgetauscht.

Der Zustand steht ruhig und ohne Symbol im oberen Menü: **Variator Ein**,
**Variator Aus** oder **Variator Fehler**. Der native Menüpunkt
**Automatische Fragen** schaltet die Funktion direkt ein oder aus. In den
Einstellungen steht außerdem die lokale Gesamtzahl
der an die KI gesendeten Karten; automatische Wiederholungsversuche werden
nicht doppelt gezählt.

## Deck für offline vorbereiten

Über **Variator → Deck für offline vorbereiten…** lassen sich die nächsten
anstehenden Karten eines Decks im Voraus erzeugen:

1. Deck wählen.
2. Anzahl wählen und **Vorbereiten** anklicken.

Standard sind 20 Karten, das Maximum beträgt 50. Variator verwendet dabei die
nächsten Karten, die Ankis Scheduler für dieses Deck tatsächlich ausgeben würde.
Während der Vorbereitung werden Internetzugang und der API-Schlüssel benötigt;
danach liegen die vorbereiteten Varianten ausschließlich im lokalen
Anki-Profil dieses Computers.

Die Offline-Vorbereitung wird **nicht über Anki Sync übertragen**. Sie steht
damit weder auf einem anderen Computer noch in AnkiMobile, AnkiDroid oder
AnkiWeb zur Verfügung. Jede tatsächlich neu erzeugte Variante nutzt die API des
gewählten Anbieters und kann abhängig vom Tarif Kosten verursachen. Variator
kennt weder Kontostand noch aktuelle Preise des Anbieters.

## Stärke der Umformulierung

- **Nah am Original:** echte, aber kleine sprachliche Änderung.
- **Leicht verändert:** mehrere Formulierungen oder die grammatische Konstruktion
  ändern sich.
- **Deutlich anders (Standard):** neue Struktur oder Abrufform; bloßer
  Synonymtausch wird abgelehnt.
- **Maximal anders:** möglichst neu entworfene Abrufform, solange exakt dasselbe
  Wissen geprüft wird.

In jeder Stufe bleiben Bedeutungs-, Einschränkungs- und Antwortleckschutz gleich
streng. Bei kurzen oder sehr eng formulierten Karten kann eine hohe Stufe keine
sichere Alternative ergeben; dann wird sofort das Original gezeigt.

## Unterstützte Anbieter

- OpenAI über die Responses API
- Google Gemini über die Interactions API
- Anthropic Claude über die Messages API
- xAI Grok über die Responses API

Das Modellfeld bleibt editierbar, weil verfügbare Modelle vom Konto und Anbieter
abhängen. Wo der Anbieter es unterstützt, deaktiviert Variator die speichernde
API-Funktion pro Anfrage. Das ersetzt keine vertragliche Zusage zur
Nullspeicherung; es gelten die Bedingungen des jeweiligen Anbieters. Googles
Gemini-Bedingungen verlangen für einen öffentlich bereitgestellten API-Client in
EWR, Schweiz und UK die Nutzung abrechnungsfähiger Paid Services.

## Datenschutz und API-Schlüssel

Variator besitzt keinen eigenen Server, keine Telemetrie und kein eigenes
Konto. Anfragen gehen direkt von Anki zum gewählten Anbieter. Gesendet werden:

- Text aus der gerenderten Kartenvorderseite;
- der für die Bedeutungsprüfung notwendige Antwortkontext;
- bei visuellen Karten die eingebetteten PNG-/JPEG-Inhalte der Vorder- und
  gegebenenfalls Antwortseite; bei layoutabhängigen Vorderseiten zusätzlich
  einen Screenshot der gerenderten Gesamtansicht;
- der feste Arbeitsauftrag zur Neuformulierung.

Ein Vorderseiten-Screenshot enthält keine Anki-Menüs, Bedienelemente oder
aufgedeckte Antwort. Ein separates Lösungsbild wird ausschließlich als
Antwortkontext zur Bedeutungsprüfung übertragen. Nicht gesendet werden Karten-
oder Notiz-IDs, Lernhistorie, Fälligkeit, lokale Bilddateinamen oder die
Anki-Benutzerkennung. Der Anbieter erhält zur Authentifizierung den
API-Schlüssel und sieht übliche Verbindungsdaten; seine Datenschutz-,
Protokollierungs- und Aufbewahrungsregeln gelten.

Ohne **API-Schlüssel merken** bleibt der Schlüssel nur bis zum Schließen von
Anki im Arbeitsspeicher. Mit dieser Option wird er auf dem Gerät im lokalen
Profil gespeichert. Unter Windows schützt Variator gespeicherte Schlüssel mit
Windows DPAPI für das aktuelle Windows-Konto. Vorhandene Klartextschlüssel
früherer Variator-Versionen werden unter Windows beim Lesen automatisch in das
geschützte Format migriert.

Auf macOS und Linux nutzt Variator als transparenten Fallback eine lokale
Profildatei. Sie ist nicht verschlüsselt und kann von Programmen mit Zugriff auf
das Anki-Profil gelesen werden. Alternativ kann auf allen Systemen die passende
Umgebungsvariable oder die reine Sitzungsspeicherung verwendet werden.
API-Schlüssel, Zustimmung und Varianten sind nach Profil getrennt und werden
**nicht über Anki Sync übertragen**.

Beim automatischen Vorbereiten am Profil- oder Deckstart können Karteninhalte
an den Anbieter gesendet werden, bevor die betreffende Karte im Reviewer
erscheint. Dies geschieht nur, wenn **Automatische Fragen** aktiv sind, eine
gültige anbieterspezifische Zustimmung vorliegt und ein API-Schlüssel verfügbar
ist. Über **Verbindung trennen & Zustimmung widerrufen** werden Zustimmung und
der lokal gespeicherte Schlüssel des aktuellen Anbieters entfernt.

## Kartenunterstützung und Grenzen

- Reine Text- und HTML-Karten werden ohne Screenshot unterstützt.
- Eingefügte PNG-/JPEG-Screenshots werden direkt in Originalqualität analysiert.
  Das gilt auch für rein bildbasierte Lösungen auf der Rückseite. Bei mehreren
  angeordneten Bildern, Diagrammen, Tabellen, Formeln oder anderem
  layoutabhängigem Material versucht Variator zusätzlich einen temporären
  Screenshot der vollständig gerenderten Vorderseite.
- Vorderseitenbilder dienen nur der KI-Analyse und werden neben einer erzeugten
  Frage nicht angezeigt. Die neue Frage muss ohne das Bild vollständig
  verständlich sein. Ist das nicht sicher möglich, verwendet Variator ohne
  Unterbrechung die unveränderte Originalkarte. Über **Original** und – sofern
  in den Einstellungen aktiviert – nach dem Aufdecken bleibt das ursprüngliche
  Bild erreichbar.
- Image Occlusion, Karten mit Eingabeantwort, Audio, Video, TTS, eingebettete
  Seiten sowie ausführungsabhängige JavaScript-Darstellungen werden
  übersprungen.
- Nur Anki Desktop zeigt die lokal vorbereiteten Varianten an.
- Anbieter-, Modell-, Quota-, Netzwerk- oder Timeoutfehler beenden eine
  Stapelvorbereitung gegebenenfalls vorzeitig; die Originalkarten bleiben
  jederzeit nutzbar.
- KI-Ausgaben können trotz Prompt und lokaler Prüfungen semantisch falsch oder
  verräterisch sein. Die Originalfrage bleibt deshalb erreichbar und wird auf
  der Rückseite standardmäßig direkt unter der neuen Frage angezeigt.

## Lokale Daten entfernen

Das Deaktivieren oder Entfernen des Add-ons stellt sofort die unveränderte
Originaldarstellung her. Lokale Varianten und gespeicherte API-Schlüssel lassen
sich unter **Werkzeuge → Erweiterungen → Variator → Konfiguration** löschen.

Eine Deinstallation löscht den Profilunterordner `fragevariator` nicht
automatisch. Wer alle lokalen Daten entfernen möchte, sollte vor der
Deinstallation beide Löschoptionen verwenden oder den Unterordner nach dem
Schließen von Anki manuell löschen.

## Entwicklung und Tests

Aus dem Projektordner lassen sich die Tests mit der Python-Standardbibliothek
ausführen:

```text
python -B -m unittest discover -s work/tests -t work
```

Für AnkiWeb muss der Inhalt des Add-on-Ordners – nicht der Ordner selbst –
direkt im `.ankiaddon`-Archiv liegen. Tests, `__pycache__` und lokale
Geheimnisse dürfen nicht enthalten sein.
