# Änderungen

## 0.5.15 – 2026-11-22

- Die Einrichtung bietet aktuelle Modelle für Gemini, OpenAI, Claude und Grok
  an. Gespeicherte Modelle bleiben auswählbar und werden beim Update beibehalten.
- Gemini 3.8 Flash und Gemini 4 Hydrogen verwenden die niedrigste unterstützte
  Denkstufe. Claude Sonnet 5.5 erhält eine einstellbare Denkstufe, die sein
  aktualisiertes API akzeptiert.
- Die unteren Reviewer-Buttons und der Einrichtungsdialog wurden mit Anki
  26.09.4 geprüft.

## 0.5.14 – 2026-09-12

- Der Original-Button übernimmt die CSS-Höhe samt zugehörigem Rahmen und
  Innenabstand vom Antwortbutton. Die bisherige Berechnung zählte Rahmen und
  Innenabstand bei Ankis Standardgestaltung doppelt und machte ihn zu hoch.
- Die gemeinsame Zeile bleibt erhalten; Höhe, Oberkante und Unterkante stimmen
  jetzt auch bei angepassten Buttons und Skalierungen überein.
- Ein gerenderter Layouttest mit Ankis CSS reproduziert den alten Fehler und
  prüft die Korrektur einschließlich Umschalten und Neuaufbau der unteren Leiste.

## 0.5.13 – 2026-09-12

- Die obere Statusanzeige heißt jetzt schlicht **Variator On**, **Variator
  Off** oder **Variator Error** (in der gewählten Sprache) und verzichtet auf
  den auffälligen Mittelpunkt.
- Der Schalter im Menü trägt statt des technischen Begriffs „Live-Modus“ den
  verständlicheren Funktionsnamen **Automatische Fragen** und verwendet
  weiterhin Ankis nativen Haken.
- Die Zustände wurden in allen fünf unterstützten Oberflächensprachen auf
  „Ein/Aus/Fehler“ beziehungsweise ihre natürlichen Übersetzungen vereinheitlicht.

## 0.5.12 – 2026-09-10

- „Original anzeigen“ sitzt jetzt als echter Nachbar von „Überspringen“ und
  „Antwort anzeigen“ in derselben mittleren Button-Zeile.
- Der bisherige feste Höhenversatz wurde entfernt. Höhe, Schrift und Grundlinie
  richten sich automatisch nach Ankis Antwortbutton – auch bei angepassten
  unteren Leisten anderer Add-ons.
- Variator verändert dabei weder Breite noch Farben der vorhandenen Buttons
  und räumt die alte separate Tabellenzelle bei einem Update zuverlässig auf.

## 0.5.11 – 2026-09-09

- Das obere Menü zeigt den Zustand jetzt dauerhaft als **Variator · Live**,
  **Variator · Aus** oder **Variator · Pausiert**.
- Der erste Menüeintrag ist ein klarer Live-Modus-Schalter; bei einer
  unterbrochenen Verbindung dient er zugleich als direkter Wiederanlauf.
- Die Einstellungen zeigen kompakt, wie viele Karten auf diesem Gerät bereits
  an die KI gesendet wurden. Anbieterinterne Wiederholungsversuche zählen nicht
  mehrfach und es werden dafür keine Karteninhalte gespeichert.
- Die Nutzungsstatistik ist rein informativ: Ein Schreibfehler kann den
  Lernablauf oder die Kartengenerierung nicht unterbrechen.

## 0.5.10 – 2026-09-07

- Die Rückseite zeigt jetzt zuerst die neue Frage, direkt darunter die
  Originalfrage zum Vergleich und anschließend die Lösung.
- Die Originalfrage wird auch bei Bildkarten und verschachtelten Vorlagen aus
  ihrer alten Position entfernt und genau einmal im Vergleichsblock gezeigt.
- In den Einstellungen kann der Vergleich auf der Rückseite ausgeblendet
  werden. Dann folgen Lösung und Bewertung direkt auf die neue Frage.
- Die Einstellung ist standardmäßig aktiviert und wird profilbezogen bewahrt.

## 0.5.9 – 2026-09-05

- Beim Aufdecken bleibt die tatsächlich gelernte KI-Frage als erstes Element
  der Rückseite sichtbar; die Lösung folgt unmittelbar darunter.
- Die Frage wird direkt hinter Ankis Antwortanker eingesetzt, damit sie auch
  nach dem automatischen Scrollen oben sichtbar bleibt.
- Bildkarten wiederholen auf der Rückseite nur die KI-Frage. Das verborgene
  Vorderseitenbild bleibt weiterhin ausschließlich über „Original“ erreichbar.
- Standard- und verschachtelte Kartenvorlagen behalten dabei ihre vorhandene
  Antwortstruktur und erhalten die KI-Frage höchstens einmal.

## 0.5.8 – 2026-09-05

- Die erste Kartenvariante startet beim Profilöffnen jetzt sofort und ist nicht
  mehr vom Abschluss des lokalen Cache-Ladens oder einer zusätzlichen
  Verzögerung abhängig.
- Variator hält im Leerlauf die jeweils nächste fällige Karte normaler Decks
  bereit. Das aktuelle beziehungsweise neu geöffnete Deck hat immer Vorrang;
  Eltern-/Unterdeck-Dopplungen und bereits vorhandene Varianten erzeugen keine
  doppelten Anbieteranfragen.
- Layoutabhängige Vorderseiten werden in ihrer tatsächlichen Inhaltshöhe
  aufgenommen. CSS-Hintergründe und Overlays werden vor dem Screenshot geladen,
  defekte Bilder fallen sofort auf sichere Originaldateien zurück und große
  High-DPI-Aufnahmen werden innerhalb des Anbieterlimits verkleinert.
- Ein beschädigter lokaler Varianten-Cache wird beim Start als wiederherstellbare
  Sicherungsdatei beiseitegelegt und automatisch neu aufgebaut. Gleichzeitige
  Cache-Zugriffe sind serialisiert.
- Nach ausgeschöpftem Rate-Limit oder vollständiger Anbieter-Nichtverfügbarkeit
  werden keine weiteren Karten derselben Warteschlange unnötig angefragt.
- Die automatische Vorbereitung und ihr Umfang werden in allen fünf
  Oberflächensprachen kurz und eindeutig beschrieben.
- 284 automatisierte Prüfungen bestehen; Paket, Prüfskript und User-Agent wurden
  auf Version 0.5.8 aktualisiert.

## 0.5.7 – 2026-09-03

- Vorderseitenbilder sind bei einer erzeugten Frage jetzt ausnahmslos
  ausgeblendet. Sie dienen nur als private Eingabe für die KI und erscheinen
  erst über **Original** beziehungsweise nach dem Aufdecken.
- Die frühere KI-Entscheidung, notwendige Diagramme oder Screenshots neben der
  neuen Frage sichtbar zu lassen, wurde entfernt. Jede Bildvariante muss als
  Text vollständig eigenständig sein; andernfalls bleibt sicher die
  unveränderte Originalkarte aktiv.
- Alte Bildvarianten mit sichtbarer Mischdarstellung werden durch eine neue
  Qualitätsversion automatisch verworfen und bei Bedarf neu erzeugt.
- Die reine Bildkarte „Lemma 9.13“ wurde erneut mit Vorder- und Lösungsbild über
  Gemini 3.5 Flash Lite geprüft. Gemini lieferte eine eigenständige Ersatzfrage
  mit dem verbindlichen Modus `replace`; alle 275 automatisierten Tests bestehen.
- Paket, Prüfskript und User-Agent auf Version 0.5.7 aktualisiert.

## 0.5.6 – 2026-09-03

- Reine Screenshot-Karten werden jetzt tatsächlich neu formuliert. Die lokale
  Qualitätsprüfung erkennt, dass `[image]` kein vergleichbarer Fragetext ist,
  und verwirft eine ansonsten gültige Bildauswertung nicht mehr pauschal.
- „Bild an die KI gesendet“ und „Bild beim Lernen anzeigen“ sind nun getrennte
  Entscheidungen: Fotografierte Fragen und unvollständige Formeln werden durch
  eine eigenständige Textfrage ersetzt; notwendige Diagramme, Markierungen oder
  räumliche Informationen bleiben sichtbar.
- Die KI muss diese Anzeigeentscheidung ausdrücklich und widerspruchsfrei
  zurückgeben. Eine Ersatzfrage, die trotzdem auf das ausgeblendete Bild
  verweist, fällt sicher auf die Originalkarte zurück.
- Die Entscheidung wird für Live- und Offline-Varianten gespeichert. Ältere
  Bildvarianten werden durch eine neue Qualitätsversion einmalig verworfen,
  damit keine alte, fehlerhafte Mischdarstellung weiterverwendet wird.
- Die reale reine Bildkarte „Lemma 9.13“ aus `3.Semester::Analysis` wurde mit
  ihrem separaten Lösungsbild erfolgreich Ende-zu-Ende über Gemini 3.5 Flash
  Lite geprüft; alle 274 automatisierten Tests bestehen.
- Paket, Prüfskript und User-Agent auf Version 0.5.6 aktualisiert.

## 0.5.5 – 2026-08-25

- Die Originalfrage lässt sich bei Fotokarten jetzt zuverlässig ein- und
  ausblenden, auch wenn Anki den Karteninhalt erst nach dem Umschalter fertig
  in die Lernansicht einsetzt.
- Ein auf der Vorderseite benötigtes Bild bleibt genau einmal sichtbar. Beim
  Aufdecken der Originalfrage erscheint nur die ursprüngliche Formulierung
  direkt unter der neuen Frage, statt denselben Screenshot ein zweites Mal zu
  rendern.
- Reine Bildfragen zeigen keinen wirkungslosen Original-Button: Das vollständige
  Originalbild ist dort ohnehin bereits sichtbar.
- Der Fehler wurde mit der realen Satz-4.28-Fotokarte aus
  `3.Semester::Analysis` sowie in einem verzögerten Browser-DOM-Lauf geprüft;
  alle 270 automatisierten Tests bestehen.
- Paket, Prüfskript und User-Agent auf Version 0.5.5 aktualisiert.

## 0.5.4 – 2026-08-25

- Normale eingefügte PNG-/JPEG-Screenshots auf der Vorderseite werden jetzt
  direkt in Originalqualität an den gewählten KI-Anbieter übertragen. Dieser
  Pfad hängt nicht mehr vom Offscreen-Rendering ab.
- Separate Lösungsbilder auf der Rückseite werden als unveränderter visueller
  Antwortkontext mitgesendet. Wiederholte Vorderseitenbilder durch `FrontSide`
  werden dabei korrekt de-dupliziert.
- Der gerenderte Gesamt-Screenshot bleibt für mehrere Bilder, Overlays,
  Diagramme, Tabellen und andere layoutabhängige Vorderseiten erhalten. Falls
  dessen Erfassung fehlschlägt, verwendet Variator sichere lokale Bildquellen
  statt die Karte zu verwerfen.
- Bildabhängige Karten werden vom KI-Prompt nicht mehr pauschal abgelehnt: Das
  sichtbare Bild bleibt unverändert, während nur der Abrufhinweis neu gestaltet
  wird. Interne Marker wie `[image]` werden nie mehr auf der Karte angezeigt.
- Alle 70 Bildkarten des Decks `3.Semester::Analysis` wurden lesend geprüft;
  Vorder- und Lösungsbilder wurden bei 70/70 Karten erkannt. Eine reale
  Integral-Karte wurde erfolgreich Ende-zu-Ende mit Gemini 3.5 Flash Lite
  neu formuliert.
- Paket, Prüfskript und User-Agent auf Version 0.5.4 aktualisiert.

## 0.5.3 – 2026-08-25

- Der Umschalter für die Originalfrage sitzt in der Lernleiste sichtbar höher
  und fügt sich ohne Größenänderung der Leiste in Ankis native Bedienelemente
  ein.
- Nicht rein textuelle Vorderseiten werden vorübergehend in ihrer tatsächlich
  gerenderten Form erfasst. Die KI erhält dadurch die vollständige Vorderseite
  mit Bildern, Tabellen, Formeln und räumlichen Beziehungen statt nur einer
  einzelnen Quelldatei.
- Die visuelle Erfassung gilt für Live-Vorlauf, Deckstart, Offline-Vorbereitung
  und manuelle Erzeugung. Reine Textkarten behalten den schnellen bisherigen
  Pfad.
- Fehlgeschlagene oder unvollständige Erfassungen fallen pro Karte sicher auf
  das Original zurück und erreichen den KI-Anbieter nicht als unvollständige
  Textanfrage.
- Datenschutztexte erklären knapp, dass nur die Kartenvorderseite als
  PNG/JPEG gesendet wird – ohne Anki-Oberfläche, Antwort oder Dateinamen.
- Paket, Prüfskript und User-Agent auf Version 0.5.3 aktualisiert.

## 0.5.2 – 2026-08-25

- Auf der Vorderseite erscheint die Originalfrage jetzt direkt unter der neu
  formulierten Frage und verwendet dieselbe ruhige Darstellung wie auf der
  Rückseite.
- Die feste Einblendung am unteren Kartenrand wurde entfernt. Frage, Hinweis
  und Antwort bleiben dadurch oben zusammen; Ankis untere Leiste verändert
  ihre Höhe nicht.
- Originalfrage und Umschalter sind fest an die aktuelle Karten-ID gebunden.
  Auch bei Überspringen, Vergraben oder schnellen Kartenwechseln kann kein
  verspäteter Klick die folgende Karte verändern.
- Aggressives Vorlagen-CSS kann Frage oder Originalhinweis nicht mehr unten,
  am Rand oder in winziger Schrift platzieren. Sichere Typografie, Farben und
  Ausrichtung der Kartenvorlage bleiben erhalten.
- Tabellenüberschriften, verbundene Zellen, Bilder und tief verschachtelte
  Vorlagen werden strukturell sicher dargestellt. Die aufgedeckte Rückseite
  behält weiterhin Antwort zuerst und Originalfrage direkt darunter.
- Paket, Prüfskript und User-Agent auf Version 0.5.2 aktualisiert.

## 0.5.1 – 2026-08-24

- Die Schaltfläche für die Originalfrage verwendet jetzt vollständig Ankis
  native Button-Größe und Abstände. Sie passt dadurch wie **Bearbeiten**,
  **Info** und **Antwort anzeigen** in die untere Leiste.
- Die Originalfrage öffnet sich als kompakte, feste Einblendung über der Karte.
  Die untere Leiste wird nicht mehr vergrößert und verdrängt weder Frage noch
  Lösung.
- Neu formulierte Vorderseiten übernehmen wieder Schriftgröße, Ausrichtung,
  Farben und relevante Präsentationshüllen der echten Kartenvorlage, ohne den
  ursprünglichen Fragetext zu kopieren. Per Vorlagen-CSS versteckte Hinweise
  oder Metadaten werden auch bei verketteten Klassen-, ID- und Elementregeln
  weder als sichtbare Frage missverstanden noch in der Originalansicht
  offengelegt. Geschlossene Hinweisbereiche bleiben zu.
- Nach dem Aufdecken bleibt Ankis Antwort-Anker erhalten. Die zu bewertende
  Lösung erscheint zuerst; die Originalfrage folgt als Kontext darunter.
  Ungewöhnlich verschachtelte Rückseiten bleiben unverändert, statt ihr HTML
  unsicher umzubauen. Eine per CSS versteckte FrontSide gilt dabei nicht mehr
  fälschlich als bereits sichtbare Originalfrage.
- Beim schnellen Wechsel von einem Eltern- in ein tief verschachteltes
  Unterdeck geht dessen automatische Vorbereitung nicht mehr verloren.
  Das gilt auch während einer manuellen Browser-Generierung; verspätete
  Ergebnisse des zuvor geöffneten Decks werden ignoriert.
- Paket, Prüfskript und User-Agent auf Version 0.5.1 aktualisiert.

## 0.5.0 – 2026-08-24

- Variator folgt standardmäßig automatisch Ankis Oberflächensprache. Deutsch,
  Englisch, Spanisch, Französisch und Russisch können in den Einstellungen auch
  fest gewählt werden.
- Karteninhalt und Oberfläche klar getrennt: Jede neue Frage bleibt unabhängig
  von der gewählten UI-Sprache in der Sprache ihrer Originalkarte.
- Verbindungseinrichtung radikal verkürzt. Anbieter, API-Schlüssel, ein kurzer
  Kostenhinweis und eine klare Zustimmung stehen im Vordergrund; Modell- und
  Datenschutzdetails bleiben bei Bedarf ausklappbar.
- Die Schlüsseloption heißt verständlich **API-Schlüssel merken (sonst nur
  diese Sitzung)**. Ohne Auswahl wird der Schlüssel beim Schließen von Anki
  verworfen, mit Auswahl bleibt er nur auf diesem Gerät erhalten.
- Unter Windows werden gemerkte API-Schlüssel mit Windows DPAPI geschützt.
  Vorhandene Klartextschlüssel aus älteren Versionen werden automatisch
  migriert.
- Ungültige API-Schlüssel, nicht verfügbare Modelle und erschöpfte Kontingente
  werden verständlich und in der gewählten Sprache erklärt. Automatische
  Anfragen pausieren dann sichtbar; wartende Anfragen werden gestoppt.
- Fehlgeschlagene unveränderte Karten werden während derselben Sitzung nicht
  erneut kostenpflichtig angefragt. Eine ausdrücklich gestartete
  Offline-Vorbereitung kann bewusst erneut versuchen.
- Umformulierungsprüfung, Antwortleckschutz und Prompt-Beispiele für Deutsch,
  Englisch, Spanisch, Französisch und Russisch vereinheitlicht; interne Bild-
  und Kürzungsmarker sind sprachneutral.
- Ein Sprachwechsel aktualisiert auch bereits geöffnete Browseraktionen und die
  Originalfrage-Schaltfläche im Reviewer ohne Anki-Neustart.
- Auf macOS und Linux bleibt die lokale Profildatei als transparenter Fallback
  erhalten. Schlüsseldateien und vorbereitete Varianten werden weiterhin nicht
  über Anki Sync übertragen.
- Paket, Prüfskript, User-Agent, Store-Text und Dokumentation auf Version 0.5.0
  aktualisiert.

## 0.4.0 – 2026-08-14

- Den sichtbaren Produktnamen auf **Variator** vereinheitlicht. Die internen
  Paket-, Datenordner- und Qt-Objektnamen mit `fragevariator` bleiben erhalten,
  damit bestehende Installationen und lokale Daten weiter funktionieren.
- Unnötige Erststart-Abfragen entfernt. Die einzige nötige Einrichtung bleibt
  die direkte Auswahl von Anbieter, Modell und API-Schlüssel.
- Bei aktivierten automatischen Fragen wird nach dem Profilstart die erste
  tatsächlich anstehende Karte des aktuell gewählten Decks vorbereitet. Beim
  Öffnen eines anderen Decks wird dessen erste anstehende Karte ebenfalls
  vorbereitet; doppelte Arbeit wird vermieden.
- **Deck für offline vorbereiten…** ergänzt. Der Nutzer wählt nur Deck und
  Anzahl; Standard sind 20, maximal 50 der als Nächstes anstehenden Karten.
- Klar kenntlich gemacht, dass Offline-Varianten nur im lokalen Desktop-Profil
  liegen, nicht über Anki Sync oder an mobile Apps übertragen werden und pro
  neu erzeugter Karte API-Kosten entstehen können.
- Die selten benötigte allgemeine Karten-Stapelaktion aus dem oberen
  Variator-Menü entfernt und durch die zielgerichtete Offline-Vorbereitung
  ersetzt.
- Paket-, Prüfskript, User-Agent, Store-Text und Dokumentation auf Version 0.4.0
  aktualisiert.

## 0.3.0 – 2026-08-14

- Den Originalfrage-Schalter auf die Größe einer echten Anki-Bedienfläche
  gebracht; geöffnete Originalfragen sind größer, linksbündig, scrollbar und in
  hellen wie dunklen Designs gut lesbar.
- Klare Zustände „Originalfrage anzeigen“ und „Originalfrage ausblenden“ sowie
  Tastatur- und Screenreader-Hinweise ergänzt.
- Die Verbindungseinrichtung verkürzt: Anbieter und Schlüssel stehen im
  Vordergrund, Modell und optionale Klartextspeicherung liegen unter
  „Erweitert“; offizielle Links führen direkt zur Schlüsselerstellung.
- Einstellungen nach Lernen, automatischer Vorbereitung sowie Verbindung und
  Datenschutz gegliedert.
- Ausschalten pausiert automatische Fragen ohne erneute Einrichtung.
  Verbindung, Zustimmung und aktueller Anbieterschlüssel können separat und
  bestätigt getrennt werden.
- Am Ende einer Lernrunde zeigt Variator kompakt, wie viele Fragen aus einem
  neuen Blickwinkel geübt wurden.
- Zusätzlich mit der Anki-/Qt-Laufzeit 26.5 geprüft.

## 0.2.3 – 2026-08-14

- Vier wählbare Umformulierungsstufen ergänzt: „Nah am Original“, „Leicht
  verändert“, „Deutlich anders“ als Standard und „Maximal anders“.
- Für jede Stufe einen eigenen Promptvertrag und eine passende lokale
  Ähnlichkeitsprüfung eingeführt; Bedeutungs- und Antwortleckschutz bleiben
  unverändert streng.
- Auswahl am Anfang der Einstellungen platziert.
- Live-Vorlauf und Browser-Erzeugung verwenden eine festgehaltene Stufe über
  den gesamten Vorgang. Ein Wechsel verwirft alte Live-Jobs und startet den
  Vorlauf sauber neu.
- Cache-Fingerabdrücke nach Stufe getrennt.

## 0.2.2 – 2026-08-14

- Vorderseite unauffällig gemacht: kein Badge und kein
  Originalfrage-Aufklappfeld mehr im Karteninhalt.
- Originalfrage-Schalter in Ankis unterer Lernleiste; nach dem Aufdecken wird
  die Originalfrage immer bei der Lösung gezeigt.
- Prompt auf echte strukturelle Neuformulierungen verschärft. Synonymtausch,
  kleine Wortänderungen, Umstellungen und lange übernommene Satzteile werden
  durch eine zusätzliche lokale Prüfung abgelehnt.
- Schutz gegen vorweggenommene Antwortteile und unvollständige Abrufaufgaben
  ergänzt; unsichere Ergebnisse fallen sofort auf die Originalkarte zurück.
- Varianten aus älteren Qualitätsregeln werden automatisch entwertet.

## 0.2.1 – 2026-08-13

- Gemini-Bildanfragen auf den stabilen Interactions-v1-Endpunkt korrigiert:
  Text und Inline-Bild werden in einem expliziten `user_input`-Schritt
  übertragen.
- Text- und Bildkarten gegen Gemini Flash und Flash Lite geprüft.

## 0.2.0 – 2026-08-12

- Live-Vorbereitung während des Lernens mit konfigurierbarem Vorlauf
  (Standard 3).
- Genau eine neue Formulierung pro Karte und einmaliger Verbrauch pro Anzeige.
- Eigenes Variator-Menü in Ankis oberer Menüleiste.
- Einklappbarer Datenschutzhinweis bei weiterhin sichtbarer Zustimmung.
- Konservative Bildunterstützung für eine einzelne, schlicht eingebundene
  lokale PNG-/JPEG-Datei bei allen vier Anbietern.
- Sicherer Sofort-Fallback auf die Originalkarte bei Cache-Miss oder Fehler.

## 0.1.0 – 2026-08-12

- Erster Desktop-MVP.
- Nicht-destruktive Variantenanzeige mit erreichbarer Originalfrage.
- Auswahl und Prüfablauf im Karten-Browser.
- Direkte Anbindung an OpenAI, Gemini, Claude und Grok.
- Lokale, profilgetrennte Speicherung ohne Anki-Sync.
- Sichere Fehlerbehandlung, strukturierte Antworten und HTML-Escaping.
