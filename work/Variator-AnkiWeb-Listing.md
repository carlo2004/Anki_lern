# Variator

**New questions. Same knowledge. Better recall.**

Variator rewrites upcoming Anki questions so you recall the answer instead of
recognising the card's familiar wording. Answers, notes, templates and
scheduling stay untouched.

## What it does

- Keeps one first due card ready per deck and prioritises the deck you open.
- Keeps the next three cards ready by default, so review does not wait for AI.
- Shows **On**, **Off** or **Error** in the top menu. Toggle it under **Automatic questions**.
- Creates exactly one checked alternative per card.
- Offers four variation levels; **Distinct** is the balanced default.
- Shows the original directly below the new question by default, with an option to hide it.
- Can prepare 1–50 upcoming cards of a deck for offline review.
- Shows a compact local count of cards sent to AI in Settings.

If a card or AI result is unsafe, unsupported or unavailable, Variator instantly
shows the original.

## Setup

Install, restart Anki, then open the **Variator** menu. Choose OpenAI, Google
Gemini, Anthropic Claude or xAI Grok and enter an API key. That is all you need.
API use may cost money under your provider's plan.

Variator automatically follows Anki's interface language. Its UI supports
English, German, Spanish, French and Russian, with a manual setting available.
Generated questions always remain in the original card's language.

## Privacy

There is no Variator server, account or telemetry. The rendered question and
necessary answer context go directly from Anki to the provider you selected.
Visual cards may also send embedded PNG/JPEG images from the front or answer;
layout-dependent fronts may add one rendered screenshot without Anki controls
or the revealed answer. Provider pricing, logging and retention terms apply.

If **Remember API key** is off, the key is kept only until Anki closes. If it is
on, it stays in this device's local Anki profile. Windows protects remembered
keys with DPAPI; old Variator plaintext keys migrate automatically. On macOS
and Linux, the profile file is the transparent fallback and can be read by
programs with profile access.

Keys and prepared questions are **not transferred by Anki Sync**. Offline
questions therefore stay on this Anki Desktop profile and do not appear in
AnkiMobile, AnkiDroid, AnkiWeb or on another computer.

## Compatibility

Text and HTML use the fast text-only path. Ordinary pasted PNG/JPEG screenshots,
including visual answers, are analysed directly at original quality. Fronts
with diagrams, tables, formulae or visual layouts can additionally use one
complete rendered screenshot.
Image Occlusion, typed-answer cards, audio/TTS, video and execution-dependent
JavaScript cards are safely skipped.

Anki Desktop 24.11 or newer. Tested with Anki 26.09.4.

Suggested tags: `ai`, `active recall`, `question variants`, `rephrasing`,
`flashcards`, `openai`, `gemini`, `claude`, `grok`.

---

## Deutsch

**Neue Fragen. Gleiches Wissen. Besserer Abruf.**

Variator formuliert anstehende Anki-Fragen neu. So erinnerst du dich an die
Antwort, statt nur das vertraute Satzbild wiederzuerkennen. Antworten,
Notizfelder, Vorlagen und Lernplanung bleiben unverändert.

- Hält je Deck eine erste fällige Karte bereit und priorisiert das geöffnete Deck.
- Standardmäßig liegen die nächsten drei Fragen ohne Wartezeit bereit.
- Zeigt **Ein**, **Aus** oder **Fehler** im oberen Menü. Unter **Automatische Fragen** lässt sich die Funktion umschalten.
- Genau eine geprüfte Alternative pro Karte.
- Vier Änderungsstufen; **Deutlich anders** ist der Standard.
- Zeigt die Originalfrage standardmäßig direkt unter der neuen Frage; optional ausblendbar.
- Optional 1–50 nächste Karten eines Decks offline vorbereiten.
- Zeigt in den Einstellungen kompakt die lokal an die KI gesendeten Karten.

Einrichtung: Im **Variator**-Menü Anbieter wählen, API-Schlüssel eingeben,
fertig. Unterstützt werden OpenAI, Gemini, Claude und Grok. API-Nutzung kann je
nach Tarif Kosten verursachen.

Die Oberfläche folgt automatisch Ankis Sprache und unterstützt Deutsch,
Englisch, Spanisch, Französisch und Russisch. Neue Fragen bleiben immer in der
Sprache der Originalkarte.

Kein Variator-Server, kein Konto, keine Telemetrie. Karteninhalt und bei
visuellen Karten eingebettete PNG-/JPEG-Bilder der Vorder- oder Antwortseite
gehen direkt an den gewählten Anbieter. Layoutabhängige Vorderseiten können
zusätzlich als Gesamt-Screenshot übertragen werden; Ankis Bedienelemente und
die aufgedeckte Antwort sind darin nicht enthalten. Ohne **API-Schlüssel
merken** gilt der Schlüssel nur bis Anki geschlossen wird. Mit der Option
bleibt er auf diesem Gerät; Windows schützt ihn mit DPAPI, macOS/Linux
verwenden eine lokal lesbare Profildatei.

Vorderseitenbilder werden nur analysiert und bei einer erzeugten Frage
ausgeblendet. Kann die KI daraus keine vollständige eigenständige Frage bilden,
bleibt die Originalkarte unverändert. Das Original ist weiterhin gezielt
aufrufbar und nach dem Aufdecken sichtbar.

Schlüssel und vorbereitete Fragen werden **nicht über Anki Sync übertragen**.
Nur Anki Desktop; Anki 24.11 oder neuer.

## Empfohlene Store-Bilder

1. Gleicher Wissenskern, deutlich andere Frage.
2. Lernansicht mit gut sichtbarer Originalfrage-Schaltfläche.
3. Kurze Verbindungseinrichtung.
4. Offline-Vorbereitung eines Decks.
