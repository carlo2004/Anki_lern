"""Tiny, dependency-free translations for Variator's desktop interface.

The add-on follows Anki's interface language by default.  A deliberately
small translation layer keeps that behaviour available even while Anki is
starting, and makes the UI testable without importing Qt.
"""

from __future__ import annotations

from typing import Any


SUPPORTED_UI_LANGUAGES: tuple[str, ...] = ("en", "de", "es", "fr", "ru")

_current_language = "en"


_EN: dict[str, str] = {
    "language.auto": "Automatic (Anki)",
    "common.provider": "Provider:",
    "common.model": "Model:",
    "common.api_key": "API key:",
    "common.show": "Show",
    "common.cancel": "Cancel",
    "common.save": "Save",
    "common.continue": "Continue",
    "common.activate": "Activate",
    "common.cards_suffix": " cards",
    "setup.title.live": "Set up Variator",
    "setup.title.batch": "Variator — Rephrase questions",
    "setup.intro.live": "Connect an AI provider. Variator prepares questions ahead.",
    "setup.intro.batch": "Connect an AI provider to create new questions.",
    "setup.api_key_placeholder": "Enter API key",
    "setup.key_link": "Create an API key at {provider} ↗",
    "setup.advanced.show": "More options",
    "setup.advanced.hide": "Fewer options",
    "setup.remember": "Remember API key (otherwise this session only)",
    "setup.remember.session": "Not remembered: available until Anki closes.",
    "setup.remember.device": "Remembered in this Anki profile on this device.",
    "setup.cost.live": "Each new question uses the provider API and may incur charges.",
    "setup.cost.batch_count": "Up to {count} API requests may incur provider charges.",
    "setup.cost.batch": "Each new question uses the provider API and may incur charges.",
    "setup.privacy.show": "Privacy",
    "setup.privacy.hide": "Hide privacy details",
    "setup.privacy.storage": (
        "If the API key is not remembered, it is kept only until Anki closes. "
        "If remembered, it is stored locally in this Anki profile and is "
        "not sent through Anki Sync. Someone with access to the profile may be "
        "able to read it."
    ),
    "setup.privacy.storage_protected": (
        "If the API key is not remembered, it is kept only until Anki closes. "
        "If remembered on Windows, it is encrypted for your Windows account "
        "and stored in this Anki profile. It is not sent through Anki Sync."
    ),
    "setup.privacy.live": (
        "When automatic questions are enabled, Variator may send rendered front "
        "text, the answer context, and, for visual cards, embedded PNG/JPEG images "
        "from the front and answer. Layout-dependent fronts may also be sent as one "
        "rendered screenshot to the selected provider, including text hidden in card "
        "HTML. At profile start, this may include the next due card from each deck; "
        "it can also start when a deck opens or while you study. Front screenshots "
        "exclude Anki controls and the revealed answer. "
        "Card IDs, review history, filenames, audio, and video are not "
        "sent. One logical request is made per card; temporary failures may cause "
        "additional HTTP attempts. Provider retention terms apply. Where supported, "
        "Variator disables API-side storage, but this is not a contractual zero-"
        "retention guarantee. Google may require billable access for publicly "
        "available Gemini API clients in the EEA, Switzerland, and the UK."
    ),
    "setup.privacy.batch": (
        "Variator sends rendered front text and the required answer context for "
        "each supported selected card to the provider. Visual cards may also send "
        "embedded front/answer images and a rendered-front PNG/JPEG screenshot. "
        "This may include text hidden in card HTML. Card "
        "IDs, review history, filenames, audio, and video are not sent."
    ),
    "setup.privacy.retries": (
        "One logical request is made per card. Temporary provider errors can cause "
        "up to {attempts} HTTP attempts for this selection."
    ),
    "setup.consent": "Allow sending card content to the {provider} API.",
    "setup.validation.model_title": "Model required",
    "setup.validation.model": "Enter a model.",
    "setup.validation.key_title": "API key required",
    "setup.validation.key": "Enter an API key.",
    "setup.validation.consent_title": "Permission required",
    "setup.validation.consent": "Allow sending card content to {provider}.",
    "offline.title": "Variator — Prepare for offline study",
    "offline.summary": (
        "Prepares the deck’s next due cards on this device. Prepared questions are "
        "not transferred to other devices by Anki Sync."
    ),
    "offline.deck_accessible": "Deck for offline preparation",
    "offline.deck_description": "Selects the deck whose next due cards are prepared.",
    "offline.no_decks": "No decks available",
    "offline.deck_label": "&Deck:",
    "offline.count_accessible": "Number of cards for offline preparation",
    "offline.count_description": "Sets how many of the next due cards are prepared.",
    "offline.count_label": "&Cards:",
    "offline.cost": "Each new question uses the provider API and may incur charges.",
    "offline.prepare": "Prepare",
    "offline.prepare_accessible": "Prepare cards for offline study",
    "review.title": "Variator — Review questions",
    "review.summary": "{generated} generated · {failed} failed. Review before saving.",
    "review.cancelled": "Generation cancelled. ",
    "review.select_all": "Select all",
    "review.select_none": "Select none",
    "review.failures": "Not generated",
    "review.card": "Card {card_id}",
    "review.failure": "Card {card_id}: {reason}",
    "review.empty": "No results to review.",
    "review.apply": "Use selection",
    "review.original_question": "<b>Original question</b>",
    "review.core_aspect": "<b>Detected core aspect</b>",
    "review.warnings": "<b>Notes</b>",
    "review.variants": "<b>Variants</b>",
    "review.use_variant": "Use this variant",
    "settings.title": "Variator — Settings",
    "settings.subtitle": "Learn the content, not the familiar wording.",
    "settings.language": "Language:",
    "settings.language_accessible": "Variator interface language",
    "settings.learning_group": "Study",
    "settings.enabled": "Use Variator while studying",
    "settings.intensity_group": "Variation",
    "settings.intensity_help": "Same content, different wording and structure.",
    "intensity.near": "Close to original",
    "intensity.light": "Slightly different",
    "intensity.distinct": "Clearly different (default)",
    "intensity.maximum": "Maximally different",
    "settings.original_after_answer": "Show original under the new question",
    "settings.prefetch_group": "Automatic preparation",
    "settings.prefetch_enabled": "Prepare new questions automatically",
    "settings.prefetch_help": "Starts with each deck’s next card, then works ahead while studying. Each new question uses the API.",
    "settings.prefetch_label": "Ahead:",
    "settings.connection_group": "Connection & privacy",
    "settings.connected": "Connected: {provider}",
    "settings.not_connected": "Not connected — automatic preparation is off.",
    "settings.connection_change": "Change connection",
    "settings.connection_setup": "Set up connection",
    "settings.disconnect": "Disconnect and withdraw permission",
    "settings.privacy_summary": "Card content is sent only after you give permission.",
    "settings.sent_cards": "Cards sent to AI: {count}",
    "settings.sent_cards_help": "Logical card requests on this device. Automatic retries are not counted again.",
    "settings.local_data_group": "Local data",
    "settings.delete_variants": "Delete saved question variants for this profile",
    "settings.delete_keys": "Delete saved API keys for this profile",
    "settings.delete_note": "You will confirm deletion after saving.",
    "settings.unchanged_note": "Original cards and Anki scheduling stay unchanged.",
    "menu.automatic_questions": "Automatic questions",
    "menu.live_switch": "Automatic questions",
    "menu.connection": "Set up connection…",
    "menu.settings": "Settings…",
    "menu.offline_prepare": "Prepare for offline study…",
    "reviewer.original": "Original question",
    "reviewer.show_original": "Show original",
    "reviewer.hide_original": "Hide original",
    "notice.preparation_running": "Variator is preparing questions…",
    "notice.live_paused": "Automatic questions off.",
    "notice.live_active": "Automatic questions on ({count} ahead)",
    "notice.live_failed": "Question preparation failed.",
    "status.live": "On",
    "status.off": "Off",
    "status.paused": "Error",
    "status.live_help": "Variator is preparing new questions automatically.",
    "status.off_help": "Variator is off. Turn on automatic questions to prepare new questions.",
    "status.paused_help": "Variator could not prepare questions. Check the connection or turn it on again to retry.",
    "error.no_profile": "Open an Anki profile first.",
    "progress.next_cards": "Finding upcoming cards…",
    "progress.ai_generating": "Creating new questions…",
    "settings.open_failed": "Could not open Variator settings.",
    "storage.unavailable": "Local storage is unavailable: {detail}",
    "storage.unknown_error": "Unknown storage error.",
}


_DE: dict[str, str] = {
    "language.auto": "Automatisch (Anki)",
    "common.provider": "Anbieter:", "common.model": "Modell:",
    "common.api_key": "API-Schlüssel:", "common.show": "Anzeigen",
    "common.cancel": "Abbrechen", "common.save": "Speichern",
    "common.continue": "Weiter", "common.activate": "Aktivieren",
    "common.cards_suffix": " Karten",
    "setup.title.live": "Variator einrichten",
    "setup.title.batch": "Variator – Fragen neu formulieren",
    "setup.intro.live": "KI-Anbieter verbinden. Variator bereitet Fragen im Voraus vor.",
    "setup.intro.batch": "KI-Anbieter verbinden und neue Fragen erstellen.",
    "setup.api_key_placeholder": "API-Schlüssel eingeben",
    "setup.key_link": "API-Schlüssel bei {provider} erstellen ↗",
    "setup.advanced.show": "Mehr Optionen", "setup.advanced.hide": "Weniger Optionen",
    "setup.remember": "API-Schlüssel merken (sonst nur diese Sitzung)",
    "setup.remember.session": "Nicht gemerkt: verfügbar, bis Anki geschlossen wird.",
    "setup.remember.device": "In diesem Anki-Profil auf diesem Gerät gemerkt.",
    "setup.cost.live": "Jede neue Frage nutzt die Anbieter-API und kann Kosten verursachen.",
    "setup.cost.batch_count": "Bis zu {count} API-Anfragen können Kosten verursachen.",
    "setup.cost.batch": "Jede neue Frage nutzt die Anbieter-API und kann Kosten verursachen.",
    "setup.privacy.show": "Datenschutz", "setup.privacy.hide": "Datenschutz ausblenden",
    "setup.privacy.storage": (
        "Ohne Merken bleibt der API-Schlüssel nur erhalten, bis Anki geschlossen "
        "wird. Beim Merken wird er lokal in diesem Anki-Profil "
        "gespeichert und nicht über Anki Sync übertragen. Personen mit Zugriff auf "
        "das Profil können ihn unter Umständen lesen."
    ),
    "setup.privacy.storage_protected": (
        "Ohne Merken bleibt der API-Schlüssel nur erhalten, bis Anki geschlossen "
        "wird. Unter Windows wird er beim Merken für dein "
        "Windows-Konto verschlüsselt in diesem Anki-Profil gespeichert. Er wird "
        "nicht über Anki Sync übertragen."
    ),
    "setup.privacy.live": (
        "Bei aktivierten automatischen Fragen kann Variator den Text der gerenderten "
        "Vorderseite, den nötigen Antwortkontext und bei visuellen Karten eingebettete "
        "PNG-/JPEG-Bilder der Vorder- und Antwortseite an den gewählten Anbieter "
        "senden. Layoutabhängige Vorderseiten können zusätzlich als gerenderter "
        "Screenshot übertragen werden, auch mit im Karten-"
        "HTML ausgeblendeten Text. Beim Profilstart kann das die nächste fällige Karte "
        "jedes Decks umfassen; außerdem kann es beim Öffnen eines Decks oder während "
        "des Lernens beginnen. Vorderseiten-Screenshots enthalten keine "
        "Anki-Bedienelemente und keine aufgedeckte Antwort. Karten-IDs, Lernverlauf, Dateinamen, Audio "
        "und Video werden nicht gesendet. Pro Karte erfolgt eine logische Anfrage; "
        "vorübergehende Fehler können weitere HTTP-Versuche auslösen. Die Regeln des "
        "Anbieters zur Aufbewahrung gelten. Wo unterstützt, deaktiviert Variator die "
        "API-seitige Speicherung; das ist keine vertragliche Nullspeicherung. Google "
        "kann für öffentlich angebotene Gemini-API-Clients in EWR, Schweiz und UK "
        "einen kostenpflichtigen Zugang verlangen."
    ),
    "setup.privacy.batch": (
        "Variator sendet den Text der gerenderten Vorderseite und den nötigen "
        "Antwortkontext jeder unterstützten ausgewählten Karte an den Anbieter. "
        "Bei visuellen Karten können zusätzlich eingebettete Vorder-/Antwortbilder "
        "und ein PNG-/JPEG-Screenshot der gerenderten Vorderseite gesendet werden. "
        "Das kann im Karten-HTML ausgeblendeten Text umfassen. Karten-IDs, "
        "Lernverlauf, Dateinamen, Audio und Video werden nicht gesendet."
    ),
    "setup.privacy.retries": (
        "Pro Karte erfolgt eine logische Anfrage. Vorübergehende Anbieterfehler "
        "können für diese Auswahl bis zu {attempts} HTTP-Versuche auslösen."
    ),
    "setup.consent": "Ich erlaube, Karteninhalte an die {provider}-API zu senden.",
    "setup.validation.model_title": "Modell fehlt", "setup.validation.model": "Bitte Modell eingeben.",
    "setup.validation.key_title": "API-Schlüssel fehlt", "setup.validation.key": "Bitte API-Schlüssel eingeben.",
    "setup.validation.consent_title": "Bestätigung fehlt",
    "setup.validation.consent": "Bitte das Senden von Karteninhalten an {provider} erlauben.",
    "offline.title": "Variator – Für offline vorbereiten",
    "offline.summary": "Bereitet die nächsten fälligen Karten des Decks auf diesem Gerät vor. Anki Sync überträgt die neuen Fragen nicht auf andere Geräte.",
    "offline.deck_accessible": "Deck für die Offline-Vorbereitung",
    "offline.deck_description": "Wählt das Deck, dessen nächste fällige Karten vorbereitet werden.",
    "offline.no_decks": "Keine Decks verfügbar", "offline.deck_label": "&Deck:",
    "offline.count_accessible": "Anzahl der Karten für die Offline-Vorbereitung",
    "offline.count_description": "Legt fest, wie viele der nächsten fälligen Karten vorbereitet werden.",
    "offline.count_label": "&Karten:",
    "offline.cost": "Jede neue Frage nutzt die Anbieter-API und kann Kosten verursachen.",
    "offline.prepare": "Vorbereiten", "offline.prepare_accessible": "Karten für die Offline-Nutzung vorbereiten",
    "review.title": "Variator – Fragen prüfen",
    "review.summary": "{generated} erzeugt · {failed} fehlgeschlagen. Vor dem Speichern prüfen.",
    "review.cancelled": "Generierung abgebrochen. ", "review.select_all": "Alle auswählen",
    "review.select_none": "Alle abwählen", "review.failures": "Nicht erzeugt",
    "review.card": "Karte {card_id}", "review.failure": "Karte {card_id}: {reason}",
    "review.empty": "Keine Ergebnisse zum Prüfen.", "review.apply": "Auswahl übernehmen",
    "review.original_question": "<b>Originalfrage</b>", "review.core_aspect": "<b>Erkannter Kernaspekt</b>",
    "review.warnings": "<b>Hinweise</b>", "review.variants": "<b>Varianten</b>",
    "review.use_variant": "Diese Variante übernehmen",
    "settings.title": "Variator – Einstellungen",
    "settings.subtitle": "Lerne den Inhalt, nicht den vertrauten Wortlaut.",
    "settings.language": "Sprache:", "settings.language_accessible": "Sprache der Variator-Oberfläche",
    "settings.learning_group": "Lernen", "settings.enabled": "Variator beim Lernen verwenden",
    "settings.intensity_group": "Abwechslung", "settings.intensity_help": "Gleicher Inhalt, anderer Wortlaut und Aufbau.",
    "intensity.near": "Nah am Original", "intensity.light": "Leicht verändert",
    "intensity.distinct": "Deutlich anders (Standard)", "intensity.maximum": "Maximal anders",
    "settings.original_after_answer": "Originalfrage unter der neuen Frage anzeigen",
    "settings.prefetch_group": "Automatische Vorbereitung",
    "settings.prefetch_enabled": "Neue Fragen automatisch vorbereiten",
    "settings.prefetch_help": "Startet mit der nächsten Karte jedes Decks und arbeitet beim Lernen voraus. Jede neue Frage nutzt die API.",
    "settings.prefetch_label": "Vorlauf:",
    "settings.connection_group": "Verbindung & Datenschutz",
    "settings.connected": "Verbunden: {provider}",
    "settings.not_connected": "Nicht verbunden – automatische Vorbereitung ist aus.",
    "settings.connection_change": "Verbindung ändern", "settings.connection_setup": "Verbindung einrichten",
    "settings.disconnect": "Trennen und Zustimmung widerrufen",
    "settings.privacy_summary": "Karteninhalte werden nur mit deiner Zustimmung gesendet.",
    "settings.sent_cards": "Karten an KI gesendet: {count}",
    "settings.sent_cards_help": "Kartenanfragen auf diesem Gerät. Automatische Wiederholungsversuche zählen nicht erneut.",
    "settings.local_data_group": "Lokale Daten",
    "settings.delete_variants": "Gespeicherte Fragevarianten dieses Profils löschen",
    "settings.delete_keys": "Gespeicherte API-Schlüssel dieses Profils löschen",
    "settings.delete_note": "Löschen wird nach dem Speichern bestätigt.",
    "settings.unchanged_note": "Originalkarten und Ankis Lernplanung bleiben unverändert.",
    "menu.automatic_questions": "Automatische Fragen", "menu.live_switch": "Automatische Fragen", "menu.connection": "Verbindung einrichten…",
    "menu.settings": "Einstellungen…", "menu.offline_prepare": "Für offline vorbereiten…",
    "reviewer.original": "Originalfrage", "reviewer.show_original": "Original anzeigen",
    "reviewer.hide_original": "Original ausblenden",
    "notice.preparation_running": "Variator bereitet Fragen vor…",
    "notice.live_paused": "Automatische Fragen aus.",
    "notice.live_active": "Automatische Fragen an ({count} im Voraus)",
    "notice.live_failed": "Vorbereitung der Frage fehlgeschlagen.",
    "status.live": "Ein", "status.off": "Aus", "status.paused": "Fehler",
    "status.live_help": "Variator bereitet neue Fragen automatisch vor.",
    "status.off_help": "Variator ist aus. Aktiviere automatische Fragen, um neue Fragen vorzubereiten.",
    "status.paused_help": "Variator konnte keine Fragen vorbereiten. Prüfe die Verbindung oder schalte ihn für einen neuen Versuch erneut ein.",
    "error.no_profile": "Bitte zuerst ein Anki-Profil öffnen.",
    "progress.next_cards": "Nächste Karten werden gesucht…", "progress.ai_generating": "Neue Fragen werden erstellt…",
    "settings.open_failed": "Variator-Einstellungen konnten nicht geöffnet werden.",
    "storage.unavailable": "Lokaler Speicher ist nicht verfügbar: {detail}",
    "storage.unknown_error": "Unbekannter Speicherfehler.",
}


_ES: dict[str, str] = {
    "language.auto": "Automático (Anki)",
    "common.provider": "Proveedor:", "common.model": "Modelo:", "common.api_key": "Clave API:",
    "common.show": "Mostrar", "common.cancel": "Cancelar", "common.save": "Guardar",
    "common.continue": "Continuar", "common.activate": "Activar", "common.cards_suffix": " tarjetas",
    "setup.title.live": "Configurar Variator", "setup.title.batch": "Variator — Reformular preguntas",
    "setup.intro.live": "Conecta un proveedor de IA. Variator prepara preguntas con antelación.",
    "setup.intro.batch": "Conecta un proveedor de IA para crear nuevas preguntas.",
    "setup.api_key_placeholder": "Introduce la clave API", "setup.key_link": "Crear una clave API en {provider} ↗",
    "setup.advanced.show": "Más opciones", "setup.advanced.hide": "Menos opciones",
    "setup.remember": "Recordar la clave API (si no, solo esta sesión)",
    "setup.remember.session": "No se recuerda: disponible hasta cerrar Anki.",
    "setup.remember.device": "Guardada en este perfil de Anki y en este dispositivo.",
    "setup.cost.live": "Cada pregunta nueva usa la API del proveedor y puede generar costes.",
    "setup.cost.batch_count": "Hasta {count} solicitudes API pueden generar costes.",
    "setup.cost.batch": "Cada pregunta nueva usa la API del proveedor y puede generar costes.",
    "setup.privacy.show": "Privacidad", "setup.privacy.hide": "Ocultar privacidad",
    "setup.privacy.storage": "Si no se recuerda, la clave API solo se conserva hasta cerrar Anki. Si se recuerda, se guarda localmente en este perfil y Anki Sync no la transfiere. Alguien con acceso al perfil podría leerla.",
    "setup.privacy.storage_protected": "Si no se recuerda, la clave API solo se conserva hasta cerrar Anki. En Windows se cifra para tu cuenta de Windows y se guarda en este perfil. Anki Sync no la transfiere.",
    "setup.privacy.live": "Con las preguntas automáticas activadas, Variator puede enviar al proveedor el texto del anverso renderizado, el contexto de respuesta necesario y, para tarjetas visuales, imágenes PNG/JPEG incrustadas del anverso y la respuesta. Los anversos dependientes del diseño también pueden enviarse como una captura renderizada, incluido texto oculto en el HTML. La captura del anverso no contiene controles de Anki ni la respuesta revelada. Al abrir el perfil, esto puede incluir la próxima tarjeta pendiente de cada mazo; también puede empezar al abrir un mazo o durante el estudio. No se envían ID, historial, nombres de archivo, audio ni vídeo. Se realiza una solicitud lógica por tarjeta; los fallos temporales pueden causar más intentos HTTP. Se aplican las reglas de conservación del proveedor. Cuando es compatible, Variator desactiva el almacenamiento de la API, pero no garantiza retención cero. Google puede exigir acceso de pago para clientes públicos de Gemini API en el EEE, Suiza y Reino Unido.",
    "setup.privacy.batch": "Variator envía al proveedor el texto del anverso renderizado y el contexto de respuesta necesario de cada tarjeta compatible. Las tarjetas visuales también pueden enviar imágenes incrustadas del anverso o la respuesta y una captura PNG/JPEG del anverso renderizado. Puede incluir texto oculto en el HTML. No se envían ID, historial, nombres de archivo, audio ni vídeo.",
    "setup.privacy.retries": "Se realiza una solicitud lógica por tarjeta. Los fallos temporales pueden causar hasta {attempts} intentos HTTP para esta selección.",
    "setup.consent": "Permitir enviar contenido de tarjetas a la API de {provider}.",
    "setup.validation.model_title": "Falta el modelo", "setup.validation.model": "Introduce un modelo.",
    "setup.validation.key_title": "Falta la clave API", "setup.validation.key": "Introduce una clave API.",
    "setup.validation.consent_title": "Falta el permiso", "setup.validation.consent": "Permite enviar contenido de tarjetas a {provider}.",
    "offline.title": "Variator — Preparar sin conexión", "offline.summary": "Prepara en este dispositivo las próximas tarjetas pendientes del mazo. Anki Sync no transfiere las preguntas a otros dispositivos.",
    "offline.deck_accessible": "Mazo para preparar sin conexión", "offline.deck_description": "Selecciona el mazo cuyas próximas tarjetas se prepararán.",
    "offline.no_decks": "No hay mazos", "offline.deck_label": "&Mazo:",
    "offline.count_accessible": "Número de tarjetas que se prepararán", "offline.count_description": "Define cuántas próximas tarjetas se prepararán.",
    "offline.count_label": "&Tarjetas:", "offline.cost": "Cada pregunta nueva usa la API del proveedor y puede generar costes.",
    "offline.prepare": "Preparar", "offline.prepare_accessible": "Preparar tarjetas sin conexión",
    "review.title": "Variator — Revisar preguntas", "review.summary": "{generated} generadas · {failed} fallidas. Revísalas antes de guardar.",
    "review.cancelled": "Generación cancelada. ", "review.select_all": "Seleccionar todo", "review.select_none": "Deseleccionar todo",
    "review.failures": "No generadas", "review.card": "Tarjeta {card_id}", "review.failure": "Tarjeta {card_id}: {reason}",
    "review.empty": "No hay resultados para revisar.", "review.apply": "Usar selección",
    "review.original_question": "<b>Pregunta original</b>", "review.core_aspect": "<b>Aspecto principal detectado</b>",
    "review.warnings": "<b>Avisos</b>", "review.variants": "<b>Variantes</b>", "review.use_variant": "Usar esta variante",
    "settings.title": "Variator — Ajustes", "settings.subtitle": "Aprende el contenido, no la redacción conocida.",
    "settings.language": "Idioma:", "settings.language_accessible": "Idioma de la interfaz de Variator",
    "settings.learning_group": "Estudio", "settings.enabled": "Usar Variator al estudiar",
    "settings.intensity_group": "Variación", "settings.intensity_help": "Mismo contenido, redacción y estructura diferentes.",
    "intensity.near": "Cerca del original", "intensity.light": "Algo diferente", "intensity.distinct": "Claramente diferente (predeterminado)", "intensity.maximum": "Máxima diferencia",
    "settings.original_after_answer": "Mostrar la pregunta original bajo la nueva",
    "settings.prefetch_group": "Preparación automática", "settings.prefetch_enabled": "Preparar preguntas automáticamente",
    "settings.prefetch_help": "Empieza con la próxima tarjeta de cada mazo y se adelanta mientras estudias. Cada pregunta nueva usa la API.", "settings.prefetch_label": "Antelación:",
    "settings.connection_group": "Conexión y privacidad", "settings.connected": "Conectado: {provider}", "settings.not_connected": "Sin conexión — la preparación automática está desactivada.",
    "settings.connection_change": "Cambiar conexión", "settings.connection_setup": "Configurar conexión", "settings.disconnect": "Desconectar y retirar permiso",
    "settings.privacy_summary": "El contenido de las tarjetas solo se envía con tu permiso.", "settings.sent_cards": "Tarjetas enviadas a la IA: {count}",
    "settings.sent_cards_help": "Solicitudes de tarjetas en este dispositivo. Los reintentos automáticos no vuelven a contar.", "settings.local_data_group": "Datos locales",
    "settings.delete_variants": "Eliminar variantes guardadas de este perfil", "settings.delete_keys": "Eliminar claves API guardadas de este perfil",
    "settings.delete_note": "Confirmarás la eliminación después de guardar.", "settings.unchanged_note": "Las tarjetas originales y la programación de Anki no cambian.",
    "menu.automatic_questions": "Preguntas automáticas", "menu.live_switch": "Preguntas automáticas", "menu.connection": "Configurar conexión…", "menu.settings": "Ajustes…", "menu.offline_prepare": "Preparar sin conexión…",
    "reviewer.original": "Pregunta original", "reviewer.show_original": "Mostrar original", "reviewer.hide_original": "Ocultar original",
    "notice.preparation_running": "Variator está preparando preguntas…", "notice.live_paused": "Preguntas automáticas desactivadas.",
    "notice.live_active": "Preguntas automáticas activadas ({count} por adelantado)", "notice.live_failed": "No se pudo preparar la pregunta.",
    "status.live": "Activado", "status.off": "Desactivado", "status.paused": "Error",
    "status.live_help": "Variator prepara nuevas preguntas automáticamente.", "status.off_help": "Variator está desactivado. Activa las preguntas automáticas para preparar preguntas nuevas.",
    "status.paused_help": "Variator no pudo preparar preguntas. Revisa la conexión o vuelve a activarlo para intentarlo de nuevo.",
    "error.no_profile": "Abre primero un perfil de Anki.", "progress.next_cards": "Buscando próximas tarjetas…", "progress.ai_generating": "Creando nuevas preguntas…",
    "settings.open_failed": "No se pudieron abrir los ajustes de Variator.", "storage.unavailable": "El almacenamiento local no está disponible: {detail}", "storage.unknown_error": "Error de almacenamiento desconocido.",
}


_FR: dict[str, str] = {
    "language.auto": "Automatique (Anki)",
    "common.provider": "Fournisseur :", "common.model": "Modèle :", "common.api_key": "Clé API :",
    "common.show": "Afficher", "common.cancel": "Annuler", "common.save": "Enregistrer",
    "common.continue": "Continuer", "common.activate": "Activer", "common.cards_suffix": " cartes",
    "setup.title.live": "Configurer Variator", "setup.title.batch": "Variator — Reformuler les questions",
    "setup.intro.live": "Connectez un fournisseur d’IA. Variator prépare les questions à l’avance.",
    "setup.intro.batch": "Connectez un fournisseur d’IA pour créer de nouvelles questions.",
    "setup.api_key_placeholder": "Saisissez la clé API", "setup.key_link": "Créer une clé API sur {provider} ↗",
    "setup.advanced.show": "Plus d’options", "setup.advanced.hide": "Moins d’options",
    "setup.remember": "Mémoriser la clé API (sinon, cette session uniquement)", "setup.remember.session": "Non mémorisée : disponible jusqu’à la fermeture d’Anki.",
    "setup.remember.device": "Mémorisée dans ce profil Anki sur cet appareil.",
    "setup.cost.live": "Chaque nouvelle question utilise l’API et peut entraîner des frais.",
    "setup.cost.batch_count": "Jusqu’à {count} appels API peuvent entraîner des frais.", "setup.cost.batch": "Chaque nouvelle question utilise l’API et peut entraîner des frais.",
    "setup.privacy.show": "Confidentialité", "setup.privacy.hide": "Masquer la confidentialité",
    "setup.privacy.storage": "Si la clé API n’est pas mémorisée, elle est conservée uniquement jusqu’à la fermeture d’Anki. Si elle est mémorisée, elle est stockée localement dans ce profil et n’est pas transmise par Anki Sync. Une personne ayant accès au profil pourrait la lire.",
    "setup.privacy.storage_protected": "Si la clé API n’est pas mémorisée, elle est conservée uniquement jusqu’à la fermeture d’Anki. Sous Windows, elle est chiffrée pour votre compte Windows et stockée dans ce profil. Anki Sync ne la transmet pas.",
    "setup.privacy.live": "Lorsque les questions automatiques sont activées, Variator peut envoyer au fournisseur le texte du recto rendu, le contexte de réponse nécessaire et, pour les cartes visuelles, les images PNG/JPEG intégrées du recto et de la réponse. Les rectos dépendant de la mise en page peuvent aussi être envoyés sous forme de capture rendue, y compris du texte masqué dans le HTML. La capture du recto ne contient ni les commandes d’Anki ni la réponse révélée. À l’ouverture du profil, cela peut inclure la prochaine carte due de chaque paquet ; l’envoi peut aussi commencer à l’ouverture d’un paquet ou pendant l’étude. Les identifiants, l’historique, les noms de fichiers, l’audio et la vidéo ne sont pas envoyés. Une requête logique est effectuée par carte ; des erreurs temporaires peuvent entraîner d’autres tentatives HTTP. Les règles de conservation du fournisseur s’appliquent. Lorsque c’est possible, Variator désactive le stockage côté API, sans garantir une conservation nulle. Google peut exiger un accès payant pour les clients Gemini API publics dans l’EEE, en Suisse et au Royaume-Uni.",
    "setup.privacy.batch": "Variator envoie au fournisseur le texte du recto rendu et le contexte de réponse nécessaire de chaque carte prise en charge. Les cartes visuelles peuvent aussi envoyer des images intégrées du recto ou de la réponse ainsi qu’une capture PNG/JPEG du recto rendu. Cela peut inclure du texte masqué dans le HTML. Les identifiants, l’historique, les noms de fichiers, l’audio et la vidéo ne sont pas envoyés.",
    "setup.privacy.retries": "Une requête logique est effectuée par carte. Des erreurs temporaires peuvent entraîner jusqu’à {attempts} tentatives HTTP pour cette sélection.",
    "setup.consent": "Autoriser l’envoi du contenu des cartes à l’API {provider}.",
    "setup.validation.model_title": "Modèle requis", "setup.validation.model": "Saisissez un modèle.",
    "setup.validation.key_title": "Clé API requise", "setup.validation.key": "Saisissez une clé API.",
    "setup.validation.consent_title": "Autorisation requise", "setup.validation.consent": "Autorisez l’envoi du contenu des cartes à {provider}.",
    "offline.title": "Variator — Préparer hors ligne", "offline.summary": "Prépare sur cet appareil les prochaines cartes dues du paquet. Anki Sync ne transfère pas les nouvelles questions vers d’autres appareils.",
    "offline.deck_accessible": "Paquet à préparer hors ligne", "offline.deck_description": "Sélectionne le paquet dont les prochaines cartes seront préparées.",
    "offline.no_decks": "Aucun paquet disponible", "offline.deck_label": "&Paquet :", "offline.count_accessible": "Nombre de cartes à préparer",
    "offline.count_description": "Définit combien de prochaines cartes seront préparées.", "offline.count_label": "&Cartes :",
    "offline.cost": "Chaque nouvelle question utilise l’API et peut entraîner des frais.", "offline.prepare": "Préparer", "offline.prepare_accessible": "Préparer des cartes hors ligne",
    "review.title": "Variator — Vérifier les questions", "review.summary": "{generated} générées · {failed} échouées. Vérifiez avant d’enregistrer.",
    "review.cancelled": "Génération annulée. ", "review.select_all": "Tout sélectionner", "review.select_none": "Tout désélectionner",
    "review.failures": "Non générées", "review.card": "Carte {card_id}", "review.failure": "Carte {card_id} : {reason}", "review.empty": "Aucun résultat à vérifier.",
    "review.apply": "Utiliser la sélection", "review.original_question": "<b>Question originale</b>", "review.core_aspect": "<b>Aspect principal détecté</b>",
    "review.warnings": "<b>Remarques</b>", "review.variants": "<b>Variantes</b>", "review.use_variant": "Utiliser cette variante",
    "settings.title": "Variator — Paramètres", "settings.subtitle": "Apprenez le contenu, pas la formulation familière.",
    "settings.language": "Langue :", "settings.language_accessible": "Langue de l’interface Variator", "settings.learning_group": "Étude",
    "settings.enabled": "Utiliser Variator pendant l’étude", "settings.intensity_group": "Variation", "settings.intensity_help": "Même contenu, formulation et structure différentes.",
    "intensity.near": "Proche de l’original", "intensity.light": "Légèrement différente", "intensity.distinct": "Clairement différente (par défaut)", "intensity.maximum": "Différence maximale",
    "settings.original_after_answer": "Afficher la question d’origine sous la nouvelle", "settings.prefetch_group": "Préparation automatique",
    "settings.prefetch_enabled": "Préparer les questions automatiquement", "settings.prefetch_help": "Commence par la prochaine carte de chaque paquet, puis anticipe pendant l’étude. Chaque nouvelle question utilise l’API.",
    "settings.prefetch_label": "À l’avance :", "settings.connection_group": "Connexion et confidentialité", "settings.connected": "Connecté : {provider}",
    "settings.not_connected": "Non connecté — la préparation automatique est désactivée.", "settings.connection_change": "Modifier la connexion",
    "settings.connection_setup": "Configurer la connexion", "settings.disconnect": "Déconnecter et retirer l’autorisation",
    "settings.privacy_summary": "Le contenu des cartes est envoyé uniquement avec votre autorisation.", "settings.sent_cards": "Cartes envoyées à l’IA : {count}",
    "settings.sent_cards_help": "Requêtes de cartes sur cet appareil. Les nouvelles tentatives automatiques ne sont pas recomptées.", "settings.local_data_group": "Données locales",
    "settings.delete_variants": "Supprimer les variantes enregistrées de ce profil", "settings.delete_keys": "Supprimer les clés API enregistrées de ce profil",
    "settings.delete_note": "Vous confirmerez la suppression après l’enregistrement.", "settings.unchanged_note": "Les cartes originales et la planification Anki restent inchangées.",
    "menu.automatic_questions": "Questions automatiques", "menu.live_switch": "Questions automatiques", "menu.connection": "Configurer la connexion…", "menu.settings": "Paramètres…", "menu.offline_prepare": "Préparer hors ligne…",
    "reviewer.original": "Question originale", "reviewer.show_original": "Afficher l’original", "reviewer.hide_original": "Masquer l’original",
    "notice.preparation_running": "Variator prépare les questions…", "notice.live_paused": "Questions automatiques désactivées.",
    "notice.live_active": "Questions automatiques activées ({count} à l’avance)", "notice.live_failed": "Échec de la préparation de la question.",
    "status.live": "Activé", "status.off": "Désactivé", "status.paused": "Erreur",
    "status.live_help": "Variator prépare automatiquement de nouvelles questions.", "status.off_help": "Variator est désactivé. Activez les questions automatiques pour préparer de nouvelles questions.",
    "status.paused_help": "Variator n’a pas pu préparer les questions. Vérifiez la connexion ou réactivez-le pour réessayer.",
    "error.no_profile": "Ouvrez d’abord un profil Anki.", "progress.next_cards": "Recherche des prochaines cartes…", "progress.ai_generating": "Création des nouvelles questions…",
    "settings.open_failed": "Impossible d’ouvrir les paramètres de Variator.", "storage.unavailable": "Stockage local indisponible : {detail}", "storage.unknown_error": "Erreur de stockage inconnue.",
}


_RU: dict[str, str] = {
    "language.auto": "Автоматически (Anki)",
    "common.provider": "Провайдер:", "common.model": "Модель:", "common.api_key": "Ключ API:",
    "common.show": "Показать", "common.cancel": "Отмена", "common.save": "Сохранить",
    "common.continue": "Продолжить", "common.activate": "Включить", "common.cards_suffix": " карт",
    "setup.title.live": "Настройка Variator", "setup.title.batch": "Variator — Переформулировать вопросы",
    "setup.intro.live": "Подключите ИИ-провайдера. Variator подготовит вопросы заранее.",
    "setup.intro.batch": "Подключите ИИ-провайдера для создания новых вопросов.",
    "setup.api_key_placeholder": "Введите ключ API", "setup.key_link": "Создать ключ API в {provider} ↗",
    "setup.advanced.show": "Больше настроек", "setup.advanced.hide": "Меньше настроек",
    "setup.remember": "Запомнить ключ API (иначе только на эту сессию)", "setup.remember.session": "Не сохранён: доступен до закрытия Anki.",
    "setup.remember.device": "Сохранён в этом профиле Anki на этом устройстве.",
    "setup.cost.live": "Каждый новый вопрос использует API провайдера и может стоить денег.",
    "setup.cost.batch_count": "До {count} запросов API могут стоить денег.", "setup.cost.batch": "Каждый новый вопрос использует API провайдера и может стоить денег.",
    "setup.privacy.show": "Конфиденциальность", "setup.privacy.hide": "Скрыть сведения",
    "setup.privacy.storage": "Если не запоминать ключ API, он хранится только до закрытия Anki. При сохранении он остаётся локально в этом профиле и не передаётся через Anki Sync. Пользователь с доступом к профилю может прочитать его.",
    "setup.privacy.storage_protected": "Если не запоминать ключ API, он хранится только до закрытия Anki. В Windows он шифруется для вашей учётной записи Windows и сохраняется в этом профиле. Anki Sync его не передаёт.",
    "setup.privacy.live": "Когда автоматические вопросы включены, Variator может отправлять провайдеру текст отображённой лицевой стороны, нужный контекст ответа и для визуальных карточек встроенные PNG/JPEG-изображения лицевой стороны и ответа. Зависящие от макета лицевые стороны также могут отправляться как отрисованный снимок, включая скрытый HTML-текст. Снимок лицевой стороны не содержит элементов управления Anki или открытого ответа. При открытии профиля это может включать следующую карточку из каждой колоды; отправка также может начаться при открытии колоды или во время учёбы. ID карточек, история повторений, имена файлов, аудио и видео не отправляются. На карточку выполняется один логический запрос; временные ошибки могут вызвать дополнительные HTTP-попытки. Действуют правила хранения провайдера. Где возможно, Variator отключает хранение на стороне API, но не гарантирует нулевое хранение. Google может требовать платный доступ для публичных клиентов Gemini API в ЕЭЗ, Швейцарии и Великобритании.",
    "setup.privacy.batch": "Variator отправляет провайдеру текст отображённой лицевой стороны и нужный контекст ответа каждой поддерживаемой карточки. Для визуальных карточек также могут отправляться встроенные изображения лицевой стороны или ответа и PNG/JPEG-снимок отрисованной лицевой стороны. Это может включать скрытый HTML-текст. ID, история повторений, имена файлов, аудио и видео не отправляются.",
    "setup.privacy.retries": "На карточку выполняется один логический запрос. Временные ошибки могут вызвать до {attempts} HTTP-попыток для этой выборки.",
    "setup.consent": "Разрешить отправку содержимого карточек в API {provider}.",
    "setup.validation.model_title": "Не указана модель", "setup.validation.model": "Укажите модель.",
    "setup.validation.key_title": "Не указан ключ API", "setup.validation.key": "Введите ключ API.",
    "setup.validation.consent_title": "Требуется разрешение", "setup.validation.consent": "Разрешите отправку содержимого карточек в {provider}.",
    "offline.title": "Variator — Подготовить офлайн", "offline.summary": "Подготавливает на этом устройстве следующие карточки колоды. Anki Sync не переносит новые вопросы на другие устройства.",
    "offline.deck_accessible": "Колода для офлайн-подготовки", "offline.deck_description": "Выбирает колоду, следующие карточки которой будут подготовлены.",
    "offline.no_decks": "Нет доступных колод", "offline.deck_label": "&Колода:", "offline.count_accessible": "Количество карточек для подготовки",
    "offline.count_description": "Задаёт количество следующих карточек для подготовки.", "offline.count_label": "&Карточки:",
    "offline.cost": "Каждый новый вопрос использует API провайдера и может стоить денег.", "offline.prepare": "Подготовить", "offline.prepare_accessible": "Подготовить карточки для офлайн-учёбы",
    "review.title": "Variator — Проверка вопросов", "review.summary": "Создано: {generated} · ошибок: {failed}. Проверьте перед сохранением.",
    "review.cancelled": "Создание отменено. ", "review.select_all": "Выбрать все", "review.select_none": "Снять выбор",
    "review.failures": "Не создано", "review.card": "Карточка {card_id}", "review.failure": "Карточка {card_id}: {reason}", "review.empty": "Нет результатов для проверки.",
    "review.apply": "Применить выбранное", "review.original_question": "<b>Исходный вопрос</b>", "review.core_aspect": "<b>Определённая основная мысль</b>",
    "review.warnings": "<b>Примечания</b>", "review.variants": "<b>Варианты</b>", "review.use_variant": "Использовать этот вариант",
    "settings.title": "Variator — Настройки", "settings.subtitle": "Учите содержание, а не знакомую формулировку.",
    "settings.language": "Язык:", "settings.language_accessible": "Язык интерфейса Variator", "settings.learning_group": "Учёба",
    "settings.enabled": "Использовать Variator при учёбе", "settings.intensity_group": "Различие", "settings.intensity_help": "То же содержание, другая формулировка и структура.",
    "intensity.near": "Близко к оригиналу", "intensity.light": "Немного иначе", "intensity.distinct": "Заметно иначе (по умолчанию)", "intensity.maximum": "Максимально иначе",
    "settings.original_after_answer": "Показывать исходный вопрос под новым", "settings.prefetch_group": "Автоматическая подготовка",
    "settings.prefetch_enabled": "Готовить вопросы автоматически", "settings.prefetch_help": "Начинает со следующей карточки каждой колоды и работает вперёд во время учёбы. Каждый новый вопрос использует API.",
    "settings.prefetch_label": "Заранее:", "settings.connection_group": "Подключение и конфиденциальность", "settings.connected": "Подключено: {provider}",
    "settings.not_connected": "Нет подключения — автоматическая подготовка выключена.", "settings.connection_change": "Изменить подключение",
    "settings.connection_setup": "Настроить подключение", "settings.disconnect": "Отключить и отозвать разрешение",
    "settings.privacy_summary": "Содержимое карточек отправляется только с вашего разрешения.", "settings.sent_cards": "Карточек отправлено ИИ: {count}",
    "settings.sent_cards_help": "Запросы карточек на этом устройстве. Автоматические повторы не учитываются снова.", "settings.local_data_group": "Локальные данные",
    "settings.delete_variants": "Удалить сохранённые варианты этого профиля", "settings.delete_keys": "Удалить сохранённые ключи API этого профиля",
    "settings.delete_note": "После сохранения нужно будет подтвердить удаление.", "settings.unchanged_note": "Исходные карточки и расписание Anki не меняются.",
    "menu.automatic_questions": "Автоматические вопросы", "menu.live_switch": "Автоматические вопросы", "menu.connection": "Настроить подключение…", "menu.settings": "Настройки…", "menu.offline_prepare": "Подготовить офлайн…",
    "reviewer.original": "Исходный вопрос", "reviewer.show_original": "Показать оригинал", "reviewer.hide_original": "Скрыть оригинал",
    "notice.preparation_running": "Variator готовит вопросы…", "notice.live_paused": "Автоматические вопросы выключены.",
    "notice.live_active": "Автоматические вопросы включены (заранее: {count})", "notice.live_failed": "Не удалось подготовить вопрос.",
    "status.live": "Вкл.", "status.off": "Выкл.", "status.paused": "Ошибка",
    "status.live_help": "Variator автоматически готовит новые вопросы.", "status.off_help": "Variator выключен. Включите автоматические вопросы для подготовки новых вопросов.",
    "status.paused_help": "Variator не смог подготовить вопросы. Проверьте подключение или включите его снова, чтобы повторить попытку.",
    "error.no_profile": "Сначала откройте профиль Anki.", "progress.next_cards": "Поиск следующих карточек…", "progress.ai_generating": "Создание новых вопросов…",
    "settings.open_failed": "Не удалось открыть настройки Variator.", "storage.unavailable": "Локальное хранилище недоступно: {detail}", "storage.unknown_error": "Неизвестная ошибка хранилища.",
}


_EN.update({
    "browser.unavailable": "The browser is not available.",
    "browser.selection_hint": "Select cards first.",
    "browser.generate": "Create new question",
    "browser.delete": "Delete saved question",
    "error.browser_open": "Could not open the browser.",
    "error.load_decks": "Could not load decks.",
    "error.next_cards": "Could not find upcoming cards.",
    "error.context_menu": "Could not open the Variator menu.",
    "error.browser_action": "The browser action failed.",
    "error.read_selection": "Could not read the selected cards.",
    "error.save_note": "Could not save the card.",
    "error.delete_variants": "Could not delete the saved questions.",
    "error.prepare_cards": "Could not prepare the cards.",
    "error.accept_results": "Could not use the generated questions.",
    "error.save_variants": "Could not save the new questions.",
    "error.settings_open": "Could not open settings.",
    "error.delete_local_variants": "Could not delete local questions.",
    "error.delete_api_keys": "Could not delete API keys.",
    "error.profile_folder": "The Anki profile folder is unavailable.",
    "error.secret_redacted": "The API key could not be read.",
    "notice.finish_review_first": "Finish the open review first.",
    "notice.no_due_cards": "No upcoming cards found.",
    "notice.offline_result": "Prepared: {prepared} · already ready: {already} · skipped: {unsuitable}",
    "notice.generation_running": "Questions are already being created.",
    "notice.select_card": "Select at least one card.",
    "notice.max_cards": "Select no more than {count} cards.",
    "notice.deleted_selected": "Deleted saved questions from {count} cards.",
    "notice.no_variants_selected": "No question selected.",
    "notice.saved_variants": "Saved new questions for {count} cards.",
    "notice.session_summary": "Reviewed {count} cards with a fresh question.",
    "notice.disconnected": "Connection removed.",
    "notice.deleted_profile": "Deleted {count} saved questions.",
    "notice.deleted_api_keys": "Saved API keys deleted.",
    "warning.key_session_only": "The key will be used for this session only: {detail}",
    "warning.revocation_clear_failed": "Permission was withdrawn, but the session key could not be cleared.",
    "warning.consent_save_failed": "Could not save permission: {detail}",
    "warning.intensity_changed_discard": "Variation changed. Older prepared questions were discarded.",
    "warning.ai_failed": "The AI request failed: {detail}",
    "warning.profile_changed": "The Anki profile changed. Results were discarded.",
    "warning.intensity_changed_not_saved": "Variation changed. These results were not saved.",
    "warning.stale_results": "Skipped {count} changed cards.",
    "warning.key_delete_failed": "Could not delete the API key: {detail}",
    "warning.consent_file_remove_failed": "Could not remove the saved permission file.",
    "warning.revocation_persist_failed": "Could not save the withdrawn permission.",
    "warning.settings_not_saved": "Settings were not saved: {detail}",
    "confirm.delete_selected": "Delete saved questions from {count} selected cards?",
    "confirm.disconnect": "Disconnect the provider and withdraw permission?",
    "confirm.delete_profile_variants": "Delete all saved questions in this profile?",
    "confirm.delete_api_keys": "Delete all saved API keys in this profile?",
    "progress.finding_cards": "Finding cards…",
    "progress.preparing_next_cards": "Preparing upcoming cards…",
    "progress.prepare_cards": "Preparing cards…",
})

_DE.update({
    "browser.unavailable": "Der Browser ist nicht verfügbar.", "browser.selection_hint": "Zuerst Karten auswählen.",
    "browser.generate": "Neue Frage erstellen", "browser.delete": "Gespeicherte Frage löschen",
    "error.browser_open": "Browser konnte nicht geöffnet werden.", "error.load_decks": "Decks konnten nicht geladen werden.",
    "error.next_cards": "Nächste Karten konnten nicht gefunden werden.", "error.context_menu": "Variator-Menü konnte nicht geöffnet werden.",
    "error.browser_action": "Browser-Aktion fehlgeschlagen.", "error.read_selection": "Ausgewählte Karten konnten nicht gelesen werden.",
    "error.save_note": "Karte konnte nicht gespeichert werden.", "error.delete_variants": "Gespeicherte Fragen konnten nicht gelöscht werden.",
    "error.prepare_cards": "Karten konnten nicht vorbereitet werden.", "error.accept_results": "Neue Fragen konnten nicht übernommen werden.",
    "error.save_variants": "Neue Fragen konnten nicht gespeichert werden.", "error.settings_open": "Einstellungen konnten nicht geöffnet werden.",
    "error.delete_local_variants": "Lokale Fragen konnten nicht gelöscht werden.", "error.delete_api_keys": "API-Schlüssel konnten nicht gelöscht werden.",
    "error.profile_folder": "Der Anki-Profilordner ist nicht verfügbar.", "error.secret_redacted": "API-Schlüssel konnte nicht gelesen werden.",
    "notice.finish_review_first": "Zuerst die offene Prüfung abschließen.", "notice.no_due_cards": "Keine nächsten Karten gefunden.",
    "notice.offline_result": "Vorbereitet: {prepared} · schon fertig: {already} · übersprungen: {unsuitable}",
    "notice.generation_running": "Fragen werden bereits erstellt.", "notice.select_card": "Mindestens eine Karte auswählen.",
    "notice.max_cards": "Höchstens {count} Karten auswählen.", "notice.deleted_selected": "Gespeicherte Fragen von {count} Karten gelöscht.",
    "notice.no_variants_selected": "Keine Frage ausgewählt.", "notice.saved_variants": "Neue Fragen für {count} Karten gespeichert.",
    "notice.session_summary": "{count} Karten mit neuer Frage gelernt.", "notice.disconnected": "Verbindung entfernt.",
    "notice.deleted_profile": "{count} gespeicherte Fragen gelöscht.", "notice.deleted_api_keys": "Gespeicherte API-Schlüssel gelöscht.",
    "warning.key_session_only": "Schlüssel gilt nur für diese Sitzung: {detail}",
    "warning.revocation_clear_failed": "Zustimmung widerrufen, Sitzungsschlüssel konnte aber nicht entfernt werden.",
    "warning.consent_save_failed": "Zustimmung konnte nicht gespeichert werden: {detail}",
    "warning.intensity_changed_discard": "Abwechslung geändert. Ältere vorbereitete Fragen wurden verworfen.",
    "warning.ai_failed": "KI-Anfrage fehlgeschlagen: {detail}", "warning.profile_changed": "Anki-Profil gewechselt. Ergebnisse wurden verworfen.",
    "warning.intensity_changed_not_saved": "Abwechslung geändert. Ergebnisse wurden nicht gespeichert.",
    "warning.stale_results": "{count} geänderte Karten übersprungen.", "warning.key_delete_failed": "API-Schlüssel konnte nicht gelöscht werden: {detail}",
    "warning.consent_file_remove_failed": "Gespeicherte Zustimmung konnte nicht entfernt werden.",
    "warning.revocation_persist_failed": "Widerruf konnte nicht gespeichert werden.", "warning.settings_not_saved": "Einstellungen wurden nicht gespeichert: {detail}",
    "confirm.delete_selected": "Gespeicherte Fragen von {count} ausgewählten Karten löschen?",
    "confirm.disconnect": "Anbieter trennen und Zustimmung widerrufen?", "confirm.delete_profile_variants": "Alle gespeicherten Fragen dieses Profils löschen?",
    "confirm.delete_api_keys": "Alle gespeicherten API-Schlüssel dieses Profils löschen?",
    "progress.finding_cards": "Karten werden gesucht…", "progress.preparing_next_cards": "Nächste Karten werden vorbereitet…", "progress.prepare_cards": "Karten werden vorbereitet…",
})

_ES.update({
    "browser.unavailable": "El explorador no está disponible.", "browser.selection_hint": "Selecciona tarjetas primero.",
    "browser.generate": "Crear pregunta nueva", "browser.delete": "Eliminar pregunta guardada",
    "error.browser_open": "No se pudo abrir el explorador.", "error.load_decks": "No se pudieron cargar los mazos.",
    "error.next_cards": "No se encontraron las próximas tarjetas.", "error.context_menu": "No se pudo abrir el menú de Variator.",
    "error.browser_action": "Falló la acción del explorador.", "error.read_selection": "No se pudieron leer las tarjetas seleccionadas.",
    "error.save_note": "No se pudo guardar la tarjeta.", "error.delete_variants": "No se pudieron eliminar las preguntas guardadas.",
    "error.prepare_cards": "No se pudieron preparar las tarjetas.", "error.accept_results": "No se pudieron usar las preguntas nuevas.",
    "error.save_variants": "No se pudieron guardar las preguntas nuevas.", "error.settings_open": "No se pudieron abrir los ajustes.",
    "error.delete_local_variants": "No se pudieron eliminar las preguntas locales.", "error.delete_api_keys": "No se pudieron eliminar las claves API.",
    "error.profile_folder": "La carpeta del perfil de Anki no está disponible.", "error.secret_redacted": "No se pudo leer la clave API.",
    "notice.finish_review_first": "Termina primero la revisión abierta.", "notice.no_due_cards": "No hay próximas tarjetas.",
    "notice.offline_result": "Preparadas: {prepared} · ya listas: {already} · omitidas: {unsuitable}",
    "notice.generation_running": "Ya se están creando preguntas.", "notice.select_card": "Selecciona al menos una tarjeta.",
    "notice.max_cards": "Selecciona como máximo {count} tarjetas.", "notice.deleted_selected": "Preguntas eliminadas de {count} tarjetas.",
    "notice.no_variants_selected": "No se seleccionó ninguna pregunta.", "notice.saved_variants": "Preguntas nuevas guardadas para {count} tarjetas.",
    "notice.session_summary": "{count} tarjetas estudiadas con una pregunta nueva.", "notice.disconnected": "Conexión eliminada.",
    "notice.deleted_profile": "Se eliminaron {count} preguntas guardadas.", "notice.deleted_api_keys": "Claves API guardadas eliminadas.",
    "warning.key_session_only": "La clave solo se usará en esta sesión: {detail}", "warning.revocation_clear_failed": "Se retiró el permiso, pero no se pudo borrar la clave de sesión.",
    "warning.consent_save_failed": "No se pudo guardar el permiso: {detail}", "warning.intensity_changed_discard": "Cambió la variación. Se descartaron preguntas preparadas anteriores.",
    "warning.ai_failed": "Falló la solicitud de IA: {detail}", "warning.profile_changed": "Cambió el perfil de Anki. Se descartaron los resultados.",
    "warning.intensity_changed_not_saved": "Cambió la variación. No se guardaron estos resultados.", "warning.stale_results": "Se omitieron {count} tarjetas modificadas.",
    "warning.key_delete_failed": "No se pudo eliminar la clave API: {detail}", "warning.consent_file_remove_failed": "No se pudo eliminar el permiso guardado.",
    "warning.revocation_persist_failed": "No se pudo guardar la retirada del permiso.", "warning.settings_not_saved": "No se guardaron los ajustes: {detail}",
    "confirm.delete_selected": "¿Eliminar las preguntas de {count} tarjetas seleccionadas?", "confirm.disconnect": "¿Desconectar el proveedor y retirar el permiso?",
    "confirm.delete_profile_variants": "¿Eliminar todas las preguntas guardadas de este perfil?", "confirm.delete_api_keys": "¿Eliminar todas las claves API guardadas de este perfil?",
    "progress.finding_cards": "Buscando tarjetas…", "progress.preparing_next_cards": "Preparando próximas tarjetas…", "progress.prepare_cards": "Preparando tarjetas…",
})

_FR.update({
    "browser.unavailable": "Le navigateur n’est pas disponible.", "browser.selection_hint": "Sélectionnez d’abord des cartes.",
    "browser.generate": "Créer une nouvelle question", "browser.delete": "Supprimer la question enregistrée",
    "error.browser_open": "Impossible d’ouvrir le navigateur.", "error.load_decks": "Impossible de charger les paquets.",
    "error.next_cards": "Impossible de trouver les prochaines cartes.", "error.context_menu": "Impossible d’ouvrir le menu Variator.",
    "error.browser_action": "Échec de l’action du navigateur.", "error.read_selection": "Impossible de lire les cartes sélectionnées.",
    "error.save_note": "Impossible d’enregistrer la carte.", "error.delete_variants": "Impossible de supprimer les questions enregistrées.",
    "error.prepare_cards": "Impossible de préparer les cartes.", "error.accept_results": "Impossible d’utiliser les nouvelles questions.",
    "error.save_variants": "Impossible d’enregistrer les nouvelles questions.", "error.settings_open": "Impossible d’ouvrir les paramètres.",
    "error.delete_local_variants": "Impossible de supprimer les questions locales.", "error.delete_api_keys": "Impossible de supprimer les clés API.",
    "error.profile_folder": "Le dossier du profil Anki n’est pas disponible.", "error.secret_redacted": "Impossible de lire la clé API.",
    "notice.finish_review_first": "Terminez d’abord la vérification ouverte.", "notice.no_due_cards": "Aucune prochaine carte trouvée.",
    "notice.offline_result": "Préparées : {prepared} · déjà prêtes : {already} · ignorées : {unsuitable}",
    "notice.generation_running": "Des questions sont déjà en cours de création.", "notice.select_card": "Sélectionnez au moins une carte.",
    "notice.max_cards": "Sélectionnez au maximum {count} cartes.", "notice.deleted_selected": "Questions supprimées de {count} cartes.",
    "notice.no_variants_selected": "Aucune question sélectionnée.", "notice.saved_variants": "Nouvelles questions enregistrées pour {count} cartes.",
    "notice.session_summary": "{count} cartes révisées avec une nouvelle question.", "notice.disconnected": "Connexion supprimée.",
    "notice.deleted_profile": "{count} questions enregistrées supprimées.", "notice.deleted_api_keys": "Clés API enregistrées supprimées.",
    "warning.key_session_only": "La clé sera utilisée pour cette session uniquement : {detail}", "warning.revocation_clear_failed": "Autorisation retirée, mais la clé de session n’a pas pu être supprimée.",
    "warning.consent_save_failed": "Impossible d’enregistrer l’autorisation : {detail}", "warning.intensity_changed_discard": "La variation a changé. Les anciennes questions préparées ont été supprimées.",
    "warning.ai_failed": "Échec de la requête IA : {detail}", "warning.profile_changed": "Le profil Anki a changé. Résultats supprimés.",
    "warning.intensity_changed_not_saved": "La variation a changé. Résultats non enregistrés.", "warning.stale_results": "{count} cartes modifiées ignorées.",
    "warning.key_delete_failed": "Impossible de supprimer la clé API : {detail}", "warning.consent_file_remove_failed": "Impossible de supprimer l’autorisation enregistrée.",
    "warning.revocation_persist_failed": "Impossible d’enregistrer le retrait de l’autorisation.", "warning.settings_not_saved": "Paramètres non enregistrés : {detail}",
    "confirm.delete_selected": "Supprimer les questions de {count} cartes sélectionnées ?", "confirm.disconnect": "Déconnecter le fournisseur et retirer l’autorisation ?",
    "confirm.delete_profile_variants": "Supprimer toutes les questions enregistrées de ce profil ?", "confirm.delete_api_keys": "Supprimer toutes les clés API enregistrées de ce profil ?",
    "progress.finding_cards": "Recherche des cartes…", "progress.preparing_next_cards": "Préparation des prochaines cartes…", "progress.prepare_cards": "Préparation des cartes…",
})

_RU.update({
    "browser.unavailable": "Браузер недоступен.", "browser.selection_hint": "Сначала выберите карточки.",
    "browser.generate": "Создать новый вопрос", "browser.delete": "Удалить сохранённый вопрос",
    "error.browser_open": "Не удалось открыть браузер.", "error.load_decks": "Не удалось загрузить колоды.",
    "error.next_cards": "Не удалось найти следующие карточки.", "error.context_menu": "Не удалось открыть меню Variator.",
    "error.browser_action": "Ошибка действия в браузере.", "error.read_selection": "Не удалось прочитать выбранные карточки.",
    "error.save_note": "Не удалось сохранить карточку.", "error.delete_variants": "Не удалось удалить сохранённые вопросы.",
    "error.prepare_cards": "Не удалось подготовить карточки.", "error.accept_results": "Не удалось применить новые вопросы.",
    "error.save_variants": "Не удалось сохранить новые вопросы.", "error.settings_open": "Не удалось открыть настройки.",
    "error.delete_local_variants": "Не удалось удалить локальные вопросы.", "error.delete_api_keys": "Не удалось удалить ключи API.",
    "error.profile_folder": "Папка профиля Anki недоступна.", "error.secret_redacted": "Не удалось прочитать ключ API.",
    "notice.finish_review_first": "Сначала завершите открытую проверку.", "notice.no_due_cards": "Следующие карточки не найдены.",
    "notice.offline_result": "Подготовлено: {prepared} · уже готово: {already} · пропущено: {unsuitable}",
    "notice.generation_running": "Вопросы уже создаются.", "notice.select_card": "Выберите хотя бы одну карточку.",
    "notice.max_cards": "Выберите не более {count} карточек.", "notice.deleted_selected": "Вопросы удалены из {count} карточек.",
    "notice.no_variants_selected": "Вопрос не выбран.", "notice.saved_variants": "Новые вопросы сохранены для {count} карточек.",
    "notice.session_summary": "Карточек с новым вопросом изучено: {count}.", "notice.disconnected": "Подключение удалено.",
    "notice.deleted_profile": "Удалено сохранённых вопросов: {count}.", "notice.deleted_api_keys": "Сохранённые ключи API удалены.",
    "warning.key_session_only": "Ключ будет использоваться только в этой сессии: {detail}", "warning.revocation_clear_failed": "Разрешение отозвано, но ключ сессии удалить не удалось.",
    "warning.consent_save_failed": "Не удалось сохранить разрешение: {detail}", "warning.intensity_changed_discard": "Степень различия изменена. Старые вопросы удалены.",
    "warning.ai_failed": "Ошибка запроса к ИИ: {detail}", "warning.profile_changed": "Профиль Anki изменился. Результаты удалены.",
    "warning.intensity_changed_not_saved": "Степень различия изменилась. Результаты не сохранены.", "warning.stale_results": "Изменённые карточки пропущены: {count}.",
    "warning.key_delete_failed": "Не удалось удалить ключ API: {detail}", "warning.consent_file_remove_failed": "Не удалось удалить сохранённое разрешение.",
    "warning.revocation_persist_failed": "Не удалось сохранить отзыв разрешения.", "warning.settings_not_saved": "Настройки не сохранены: {detail}",
    "confirm.delete_selected": "Удалить вопросы из {count} выбранных карточек?", "confirm.disconnect": "Отключить провайдера и отозвать разрешение?",
    "confirm.delete_profile_variants": "Удалить все сохранённые вопросы этого профиля?", "confirm.delete_api_keys": "Удалить все сохранённые ключи API этого профиля?",
    "progress.finding_cards": "Поиск карточек…", "progress.preparing_next_cards": "Подготовка следующих карточек…", "progress.prepare_cards": "Подготовка карточек…",
})


# Failure reasons are shown inside the review dialog, so they follow the
# Variator interface language as well.  Model-provided card content remains
# untouched and is deliberately not routed through this table.
_EN.update({
    "setup.remember.environment": "{variable} is managed outside Variator.",
    "setup.privacy.storage_environment": "{variable} is provided by your operating system and managed outside Variator. Variator does not store this key.",
    "notice.connection_saved": "Connection saved.",
    "warning.remembered_key_unavailable": "The remembered API key could not be loaded securely. Enter it again.",
    "warning.old_key_remove_failed_session_active": "New key active for this session. The old remembered key could not be removed.",
    "failure.typed_answer": "Cards with Anki’s typed-answer field are not changed.",
    "failure.image_occlusion": "Image Occlusion cards are not supported.",
    "failure.simple_image": "Images are supported only as one unchanged local PNG or JPEG without image layout.",
    "failure.unsupported_media": "Cards with audio, video, embedded pages, or TTS are not rephrased.",
    "failure.images_live_only": "Cards with images are supported only during automatic preparation.",
    "failure.image_unreadable": "The rendered front could not be captured safely.",
    "failure.front_no_text": "The rendered front contains no readable text.",
    "failure.answer_no_text": "The rendered back contains no readable answer text.",
    "failure.image_path_unsafe": "An image path left Anki’s media folder.",
    "failure.image_too_large": "A card image is too large for secure transfer.",
    "failure.images_too_large": "The card images are too large in total.",
    "failure.too_many_images": "The card contains too many images for one request.",
    "failure.image_changed": "A card image changed while it was being prepared.",
    "failure.image_invalid": "A card image file has an invalid format.",
    "failure.card_unreadable": "The card could not be read: {detail}",
    "redaction.api_key": "[API key removed]",
    "provider_error.auth": "The API key was rejected.",
    "provider_error.permission": "The provider denied access.",
    "provider_error.quota": "The API quota or credit is exhausted.",
    "provider_error.rate_limit": "The provider is busy. Try again shortly.",
    "provider_error.bad_request": "The provider rejected the request.",
    "provider_error.model_not_found": "The selected model is unavailable.",
    "provider_error.timeout": "The provider took too long to respond.",
    "provider_error.network": "The provider could not be reached.",
    "provider_error.unavailable": "The provider is temporarily unavailable.",
    "provider_error.refusal": "The provider declined to rephrase this card.",
    "provider_error.incomplete": "The provider returned an incomplete answer.",
    "provider_error.invalid_response": "The provider returned an invalid answer.",
    "provider_error.cancelled": "The request was cancelled.",
    "provider_error.unknown": "The AI request failed.",
    "parse.empty_response": "The AI returned no answer.",
    "parse.invalid_json": "The AI answer did not contain a valid JSON object.",
    "parse.unsupported_default": "This card cannot be rephrased safely.",
    "parse.unknown_status": "Unknown AI response status: {status}",
    "parse.missing_equivalence_check": "The AI answer has no clear equivalence check.",
    "parse.equivalence_unconfirmed": "The AI could not confirm equivalent content.",
    "parse.missing_answer_leak_check": "The AI answer has no clear answer-hint check.",
    "parse.answer_revealed": "The new question would reveal part of the answer.",
    "parse.missing_distance_check": "The AI answer has no clear difference check.",
    "parse.distance_unconfirmed": "The AI could not create a question at the selected variation level.",
    "parse.missing_change_strategy": "The structural change strategy is missing.",
    "parse.missing_visual_contract": "The AI returned no safe display decision for the front image.",
    "parse.inconsistent_visual_contract": "The AI returned an inconsistent display decision for the front image.",
    "parse.hidden_visual_reference": "The new question still referred to an image that would be hidden. The original card is shown instead.",
    "parse.missing_core_aspect": "The AI answer is missing the core aspect.",
    "parse.missing_variants": "The AI answer contains no variants list.",
    "parse.answer_leak_local": "The generated question might reveal part of the answer. The original card is shown instead.",
    "parse.too_similar_local": "The generated question was still too similar to the original. The original card is shown instead.",
    "parse.no_usable_question": "The AI returned no usable new question.",
    "parse.partial_variants": "Only {actual} of {requested} variants were clearly usable.",
    "parse.possible_answer_leak": "A variant may reveal a short answer term; please check it.",
})

_DE.update({
    "setup.remember.environment": "{variable} wird außerhalb von Variator verwaltet.",
    "setup.privacy.storage_environment": "{variable} wird von deinem Betriebssystem bereitgestellt und außerhalb von Variator verwaltet. Variator speichert diesen Schlüssel nicht.",
    "notice.connection_saved": "Verbindung gespeichert.",
    "warning.remembered_key_unavailable": "Der gemerkte API-Schlüssel konnte nicht sicher geladen werden. Bitte neu eingeben.",
    "warning.old_key_remove_failed_session_active": "Neuer Schlüssel für diese Sitzung aktiv. Der alte gemerkte Schlüssel konnte nicht entfernt werden.",
    "failure.typed_answer": "Karten mit Ankis Eingabefeld für getippte Antworten werden nicht verändert.",
    "failure.image_occlusion": "Image-Occlusion-Karten werden nicht unterstützt.",
    "failure.simple_image": "Bilder werden nur als einzelne, unveränderte lokale PNG- oder JPEG-Datei ohne Bildlayout unterstützt.",
    "failure.unsupported_media": "Karten mit Audio, Video, eingebetteten Seiten oder TTS werden nicht umformuliert.",
    "failure.images_live_only": "Karten mit Bildern werden nur bei der automatischen Vorbereitung unterstützt.",
    "failure.image_unreadable": "Die gerenderte Vorderseite konnte nicht sicher aufgenommen werden.",
    "failure.front_no_text": "Die gerenderte Vorderseite enthält keinen lesbaren Text.",
    "failure.answer_no_text": "Die gerenderte Rückseite enthält keinen lesbaren Antworttext.",
    "failure.image_path_unsafe": "Ein Bildpfad verließ den Anki-Medienordner.",
    "failure.image_too_large": "Ein Kartenbild ist für die sichere Übertragung zu groß.",
    "failure.images_too_large": "Die Bilder dieser Karte sind zusammen zu groß.",
    "failure.too_many_images": "Die Karte enthält zu viele Bilder für eine Anfrage.",
    "failure.image_changed": "Ein Kartenbild änderte sich während der Vorbereitung.",
    "failure.image_invalid": "Eine Kartenbilddatei besitzt ein ungültiges Format.",
    "failure.card_unreadable": "Die Karte konnte nicht gelesen werden: {detail}",
    "redaction.api_key": "[API-Schlüssel entfernt]",
    "provider_error.auth": "Der API-Schlüssel wurde abgelehnt.",
    "provider_error.permission": "Der Anbieter hat den Zugriff verweigert.",
    "provider_error.quota": "API-Kontingent oder Guthaben ist aufgebraucht.",
    "provider_error.rate_limit": "Der Anbieter ist ausgelastet. Bitte gleich erneut versuchen.",
    "provider_error.bad_request": "Der Anbieter hat die Anfrage abgelehnt.",
    "provider_error.model_not_found": "Das gewählte Modell ist nicht verfügbar.",
    "provider_error.timeout": "Der Anbieter hat zu lange nicht geantwortet.",
    "provider_error.network": "Der Anbieter ist nicht erreichbar.",
    "provider_error.unavailable": "Der Anbieter ist vorübergehend nicht verfügbar.",
    "provider_error.refusal": "Der Anbieter wollte diese Karte nicht umformulieren.",
    "provider_error.incomplete": "Der Anbieter hat unvollständig geantwortet.",
    "provider_error.invalid_response": "Der Anbieter hat ungültig geantwortet.",
    "provider_error.cancelled": "Die Anfrage wurde abgebrochen.",
    "provider_error.unknown": "Die KI-Anfrage ist fehlgeschlagen.",
    "parse.empty_response": "Die KI hat keine Antwort geliefert.",
    "parse.invalid_json": "Die KI-Antwort enthielt kein gültiges JSON-Objekt.",
    "parse.unsupported_default": "Diese Karte lässt sich nicht sicher umformulieren.",
    "parse.unknown_status": "Unbekannter Antwortstatus der KI: {status}",
    "parse.missing_equivalence_check": "Die KI-Antwort enthält keine eindeutige Gleichwertigkeitsprüfung.",
    "parse.equivalence_unconfirmed": "Die KI konnte die inhaltliche Gleichwertigkeit nicht sicher bestätigen.",
    "parse.missing_answer_leak_check": "Die KI-Antwort enthält keine eindeutige Prüfung auf Antwort-Hinweise.",
    "parse.answer_revealed": "Die neue Frage würde einen Teil der Antwort vorwegnehmen.",
    "parse.missing_distance_check": "Die KI-Antwort enthält keine eindeutige Distanzprüfung.",
    "parse.distance_unconfirmed": "Die KI konnte keine Frage in der gewählten Änderungsstufe erzeugen.",
    "parse.missing_change_strategy": "Die strukturelle Änderungsstrategie fehlt.",
    "parse.missing_visual_contract": "Die KI lieferte keine sichere Anzeigeentscheidung für das Vorderseitenbild.",
    "parse.inconsistent_visual_contract": "Die KI lieferte eine widersprüchliche Anzeigeentscheidung für das Vorderseitenbild.",
    "parse.hidden_visual_reference": "Die neue Frage verwies noch auf ein ausgeblendetes Bild. Deshalb wird die Originalkarte gezeigt.",
    "parse.missing_core_aspect": "Der Kernaspekt fehlt in der KI-Antwort.",
    "parse.missing_variants": "Die KI-Antwort enthält keine Variantenliste.",
    "parse.answer_leak_local": "Die erzeugte Frage könnte einen Teil der Antwort vorwegnehmen. Deshalb wird die Originalkarte gezeigt.",
    "parse.too_similar_local": "Die erzeugte Frage war der Originalfrage noch zu ähnlich. Deshalb wird die Originalkarte gezeigt.",
    "parse.no_usable_question": "Die KI lieferte keine neue, verwendbare Frage.",
    "parse.partial_variants": "Nur {actual} von {requested} Varianten waren eindeutig verwendbar.",
    "parse.possible_answer_leak": "Eine Variante könnte einen kurzen Antwortbegriff verraten; bitte prüfen.",
})

_ES.update({
    "setup.remember.environment": "{variable} se gestiona fuera de Variator.",
    "setup.privacy.storage_environment": "El sistema operativo proporciona {variable} y la gestiona fuera de Variator. Variator no guarda esta clave.",
    "notice.connection_saved": "Conexión guardada.",
    "warning.remembered_key_unavailable": "No se pudo cargar de forma segura la clave API guardada. Introdúcela de nuevo.",
    "warning.old_key_remove_failed_session_active": "La clave nueva está activa en esta sesión. No se pudo eliminar la clave guardada anterior.",
    "failure.typed_answer": "Las tarjetas con el campo de respuesta escrita de Anki no se modifican.",
    "failure.image_occlusion": "Las tarjetas de oclusión de imágenes no son compatibles.",
    "failure.simple_image": "Solo se admite una imagen PNG o JPEG local sin modificar ni maquetar.",
    "failure.unsupported_media": "No se reformulan tarjetas con audio, vídeo, páginas incrustadas o TTS.",
    "failure.images_live_only": "Las tarjetas con imágenes solo se admiten durante la preparación automática.",
    "failure.image_unreadable": "No se pudo capturar de forma segura el anverso renderizado.",
    "failure.front_no_text": "El anverso renderizado no contiene texto legible.",
    "failure.answer_no_text": "El reverso renderizado no contiene texto de respuesta legible.",
    "failure.image_path_unsafe": "Una ruta de imagen salió de la carpeta multimedia de Anki.",
    "failure.image_too_large": "Una imagen de la tarjeta es demasiado grande para transferirla de forma segura.",
    "failure.images_too_large": "Las imágenes de la tarjeta son demasiado grandes en total.",
    "failure.too_many_images": "La tarjeta contiene demasiadas imágenes para una solicitud.",
    "failure.image_changed": "Una imagen de la tarjeta cambió durante la preparación.",
    "failure.image_invalid": "Un archivo de imagen de la tarjeta tiene un formato no válido.",
    "failure.card_unreadable": "No se pudo leer la tarjeta: {detail}",
    "redaction.api_key": "[clave API eliminada]",
    "provider_error.auth": "La clave API fue rechazada.",
    "provider_error.permission": "El proveedor denegó el acceso.",
    "provider_error.quota": "Se agotó la cuota o el saldo de la API.",
    "provider_error.rate_limit": "El proveedor está ocupado. Inténtalo de nuevo en breve.",
    "provider_error.bad_request": "El proveedor rechazó la solicitud.",
    "provider_error.model_not_found": "El modelo seleccionado no está disponible.",
    "provider_error.timeout": "El proveedor tardó demasiado en responder.",
    "provider_error.network": "No se pudo contactar con el proveedor.",
    "provider_error.unavailable": "El proveedor no está disponible temporalmente.",
    "provider_error.refusal": "El proveedor rechazó reformular esta tarjeta.",
    "provider_error.incomplete": "El proveedor devolvió una respuesta incompleta.",
    "provider_error.invalid_response": "El proveedor devolvió una respuesta no válida.",
    "provider_error.cancelled": "Se canceló la solicitud.",
    "provider_error.unknown": "Falló la solicitud de IA.",
    "parse.empty_response": "La IA no devolvió ninguna respuesta.",
    "parse.invalid_json": "La respuesta de la IA no contenía un objeto JSON válido.",
    "parse.unsupported_default": "Esta tarjeta no se puede reformular de forma segura.",
    "parse.unknown_status": "Estado de respuesta de la IA desconocido: {status}",
    "parse.missing_equivalence_check": "La respuesta de la IA no incluye una comprobación clara de equivalencia.",
    "parse.equivalence_unconfirmed": "La IA no pudo confirmar la equivalencia del contenido.",
    "parse.missing_answer_leak_check": "La respuesta de la IA no incluye una comprobación clara de pistas sobre la respuesta.",
    "parse.answer_revealed": "La nueva pregunta revelaría parte de la respuesta.",
    "parse.missing_distance_check": "La respuesta de la IA no incluye una comprobación clara del grado de cambio.",
    "parse.distance_unconfirmed": "La IA no pudo crear una pregunta con el grado de cambio seleccionado.",
    "parse.missing_change_strategy": "Falta la estrategia de cambio estructural.",
    "parse.missing_visual_contract": "La IA no devolvió una decisión segura sobre cómo mostrar la imagen del anverso.",
    "parse.inconsistent_visual_contract": "La IA devolvió una decisión incoherente sobre la imagen del anverso.",
    "parse.hidden_visual_reference": "La nueva pregunta aún hacía referencia a una imagen oculta. Se muestra la tarjeta original.",
    "parse.missing_core_aspect": "Falta el aspecto central en la respuesta de la IA.",
    "parse.missing_variants": "La respuesta de la IA no contiene una lista de variantes.",
    "parse.answer_leak_local": "La pregunta generada podría revelar parte de la respuesta. Se muestra la tarjeta original.",
    "parse.too_similar_local": "La pregunta generada seguía pareciéndose demasiado a la original. Se muestra la tarjeta original.",
    "parse.no_usable_question": "La IA no devolvió ninguna pregunta nueva utilizable.",
    "parse.partial_variants": "Solo {actual} de {requested} variantes eran claramente utilizables.",
    "parse.possible_answer_leak": "Una variante podría revelar un término breve de la respuesta; revísala.",
})

_FR.update({
    "setup.remember.environment": "{variable} est gérée hors de Variator.",
    "setup.privacy.storage_environment": "{variable} est fournie par votre système d’exploitation et gérée hors de Variator. Variator ne stocke pas cette clé.",
    "notice.connection_saved": "Connexion enregistrée.",
    "warning.remembered_key_unavailable": "Impossible de charger la clé API enregistrée de manière sécurisée. Saisissez-la à nouveau.",
    "warning.old_key_remove_failed_session_active": "La nouvelle clé est active pour cette session. Impossible de supprimer l’ancienne clé enregistrée.",
    "failure.typed_answer": "Les cartes avec le champ de réponse saisie d’Anki ne sont pas modifiées.",
    "failure.image_occlusion": "Les cartes d’occlusion d’image ne sont pas prises en charge.",
    "failure.simple_image": "Seule une image PNG ou JPEG locale, inchangée et sans mise en page, est prise en charge.",
    "failure.unsupported_media": "Les cartes avec audio, vidéo, page intégrée ou TTS ne sont pas reformulées.",
    "failure.images_live_only": "Les cartes avec images sont prises en charge uniquement pendant la préparation automatique.",
    "failure.image_unreadable": "Le recto rendu n’a pas pu être capturé de manière sûre.",
    "failure.front_no_text": "Le recto rendu ne contient aucun texte lisible.",
    "failure.answer_no_text": "Le verso rendu ne contient aucun texte de réponse lisible.",
    "failure.image_path_unsafe": "Un chemin d’image est sorti du dossier multimédia d’Anki.",
    "failure.image_too_large": "Une image de la carte est trop volumineuse pour un transfert sécurisé.",
    "failure.images_too_large": "Les images de la carte sont trop volumineuses au total.",
    "failure.too_many_images": "La carte contient trop d’images pour une requête.",
    "failure.image_changed": "Une image de la carte a changé pendant la préparation.",
    "failure.image_invalid": "Un fichier image de la carte a un format non valide.",
    "failure.card_unreadable": "Impossible de lire la carte : {detail}",
    "redaction.api_key": "[clé API supprimée]",
    "provider_error.auth": "La clé API a été refusée.",
    "provider_error.permission": "Le fournisseur a refusé l’accès.",
    "provider_error.quota": "Le quota ou le crédit de l’API est épuisé.",
    "provider_error.rate_limit": "Le fournisseur est occupé. Réessayez dans un instant.",
    "provider_error.bad_request": "Le fournisseur a refusé la requête.",
    "provider_error.model_not_found": "Le modèle sélectionné n’est pas disponible.",
    "provider_error.timeout": "Le fournisseur a mis trop de temps à répondre.",
    "provider_error.network": "Le fournisseur est inaccessible.",
    "provider_error.unavailable": "Le fournisseur est temporairement indisponible.",
    "provider_error.refusal": "Le fournisseur a refusé de reformuler cette carte.",
    "provider_error.incomplete": "Le fournisseur a renvoyé une réponse incomplète.",
    "provider_error.invalid_response": "Le fournisseur a renvoyé une réponse non valide.",
    "provider_error.cancelled": "La requête a été annulée.",
    "provider_error.unknown": "La requête d’IA a échoué.",
    "parse.empty_response": "L’IA n’a fourni aucune réponse.",
    "parse.invalid_json": "La réponse de l’IA ne contenait aucun objet JSON valide.",
    "parse.unsupported_default": "Cette carte ne peut pas être reformulée de manière sûre.",
    "parse.unknown_status": "État de réponse de l’IA inconnu : {status}",
    "parse.missing_equivalence_check": "La réponse de l’IA ne contient aucune vérification claire d’équivalence.",
    "parse.equivalence_unconfirmed": "L’IA n’a pas pu confirmer l’équivalence du contenu.",
    "parse.missing_answer_leak_check": "La réponse de l’IA ne contient aucune vérification claire des indices de réponse.",
    "parse.answer_revealed": "La nouvelle question révélerait une partie de la réponse.",
    "parse.missing_distance_check": "La réponse de l’IA ne contient aucune vérification claire du degré de changement.",
    "parse.distance_unconfirmed": "L’IA n’a pas pu créer de question au degré de changement choisi.",
    "parse.missing_change_strategy": "La stratégie de changement structurel est absente.",
    "parse.missing_visual_contract": "L’IA n’a fourni aucune décision sûre pour l’affichage de l’image du recto.",
    "parse.inconsistent_visual_contract": "L’IA a fourni une décision incohérente pour l’image du recto.",
    "parse.hidden_visual_reference": "La nouvelle question faisait encore référence à une image masquée. La carte originale est affichée.",
    "parse.missing_core_aspect": "L’aspect central manque dans la réponse de l’IA.",
    "parse.missing_variants": "La réponse de l’IA ne contient aucune liste de variantes.",
    "parse.answer_leak_local": "La question générée pourrait révéler une partie de la réponse. La carte originale est affichée.",
    "parse.too_similar_local": "La question générée ressemblait encore trop à l’originale. La carte originale est affichée.",
    "parse.no_usable_question": "L’IA n’a fourni aucune nouvelle question utilisable.",
    "parse.partial_variants": "Seules {actual} variantes sur {requested} étaient clairement utilisables.",
    "parse.possible_answer_leak": "Une variante pourrait révéler un terme court de la réponse ; vérifiez-la.",
})

_RU.update({
    "setup.remember.environment": "Переменная {variable} управляется вне Variator.",
    "setup.privacy.storage_environment": "Переменная {variable} предоставляется операционной системой и управляется вне Variator. Variator не сохраняет этот ключ.",
    "notice.connection_saved": "Подключение сохранено.",
    "warning.remembered_key_unavailable": "Не удалось безопасно загрузить сохранённый ключ API. Введите его снова.",
    "warning.old_key_remove_failed_session_active": "Новый ключ действует в этом сеансе. Не удалось удалить ранее сохранённый ключ.",
    "failure.typed_answer": "Карточки с полем Anki для ввода ответа не изменяются.",
    "failure.image_occlusion": "Карточки с закрытием частей изображения не поддерживаются.",
    "failure.simple_image": "Поддерживается только одно неизменённое локальное изображение PNG или JPEG без сложной разметки.",
    "failure.unsupported_media": "Карточки с аудио, видео, встроенными страницами или TTS не переформулируются.",
    "failure.images_live_only": "Карточки с изображениями поддерживаются только при автоматической подготовке.",
    "failure.image_unreadable": "Не удалось безопасно сделать снимок отображённой лицевой стороны.",
    "failure.front_no_text": "На отображённой лицевой стороне нет читаемого текста.",
    "failure.answer_no_text": "На отображённой обратной стороне нет читаемого текста ответа.",
    "failure.image_path_unsafe": "Путь к изображению вышел за пределы папки медиафайлов Anki.",
    "failure.image_too_large": "Изображение карточки слишком велико для безопасной передачи.",
    "failure.images_too_large": "Общий размер изображений карточки слишком велик.",
    "failure.too_many_images": "В карточке слишком много изображений для одного запроса.",
    "failure.image_changed": "Изображение карточки изменилось во время подготовки.",
    "failure.image_invalid": "Файл изображения карточки имеет недопустимый формат.",
    "failure.card_unreadable": "Не удалось прочитать карточку: {detail}",
    "redaction.api_key": "[ключ API удалён]",
    "provider_error.auth": "Ключ API отклонён.",
    "provider_error.permission": "Провайдер отказал в доступе.",
    "provider_error.quota": "Квота или средства API исчерпаны.",
    "provider_error.rate_limit": "Провайдер занят. Повторите попытку чуть позже.",
    "provider_error.bad_request": "Провайдер отклонил запрос.",
    "provider_error.model_not_found": "Выбранная модель недоступна.",
    "provider_error.timeout": "Провайдер слишком долго не отвечал.",
    "provider_error.network": "Не удалось связаться с провайдером.",
    "provider_error.unavailable": "Провайдер временно недоступен.",
    "provider_error.refusal": "Провайдер отказался переформулировать эту карточку.",
    "provider_error.incomplete": "Провайдер вернул неполный ответ.",
    "provider_error.invalid_response": "Провайдер вернул недопустимый ответ.",
    "provider_error.cancelled": "Запрос отменён.",
    "provider_error.unknown": "Не удалось выполнить запрос к ИИ.",
    "parse.empty_response": "ИИ не вернул ответ.",
    "parse.invalid_json": "Ответ ИИ не содержал допустимый объект JSON.",
    "parse.unsupported_default": "Эту карточку нельзя безопасно переформулировать.",
    "parse.unknown_status": "Неизвестный статус ответа ИИ: {status}",
    "parse.missing_equivalence_check": "В ответе ИИ нет однозначной проверки эквивалентности.",
    "parse.equivalence_unconfirmed": "ИИ не смог подтвердить эквивалентность содержания.",
    "parse.missing_answer_leak_check": "В ответе ИИ нет однозначной проверки подсказок к ответу.",
    "parse.answer_revealed": "Новый вопрос раскрыл бы часть ответа.",
    "parse.missing_distance_check": "В ответе ИИ нет однозначной проверки степени изменения.",
    "parse.distance_unconfirmed": "ИИ не смог создать вопрос с выбранной степенью изменения.",
    "parse.missing_change_strategy": "Не указана стратегия структурного изменения.",
    "parse.missing_visual_contract": "ИИ не вернул безопасное решение о показе изображения на лицевой стороне.",
    "parse.inconsistent_visual_contract": "ИИ вернул противоречивое решение о показе изображения на лицевой стороне.",
    "parse.hidden_visual_reference": "Новый вопрос всё ещё ссылался на скрытое изображение. Вместо него показана исходная карточка.",
    "parse.missing_core_aspect": "В ответе ИИ отсутствует основной аспект.",
    "parse.missing_variants": "В ответе ИИ отсутствует список вариантов.",
    "parse.answer_leak_local": "Созданный вопрос мог бы раскрыть часть ответа. Вместо него показана исходная карточка.",
    "parse.too_similar_local": "Созданный вопрос всё ещё слишком похож на исходный. Вместо него показана исходная карточка.",
    "parse.no_usable_question": "ИИ не вернул новый пригодный вопрос.",
    "parse.partial_variants": "Однозначно пригодны только {actual} из {requested} вариантов.",
    "parse.possible_answer_leak": "Вариант может раскрыть короткий термин из ответа; проверьте его.",
})


_EN.update({
    "notice.live_failed_detail": "{reason}\nCheck the connection in Variator settings.",
    "warning.offline_failed": "Offline preparation stopped: {reason}\nCheck the connection in Variator settings.",
})

_DE.update({
    "notice.live_failed_detail": "{reason}\nPrüfe die Verbindung in den Variator-Einstellungen.",
    "warning.offline_failed": "Offline-Vorbereitung gestoppt: {reason}\nPrüfe die Verbindung in den Variator-Einstellungen.",
})

_ES.update({
    "notice.live_failed_detail": "{reason}\nComprueba la conexión en los ajustes de Variator.",
    "warning.offline_failed": "Se detuvo la preparación sin conexión: {reason}\nComprueba la conexión en los ajustes de Variator.",
})

_FR.update({
    "notice.live_failed_detail": "{reason}\nVérifiez la connexion dans les paramètres de Variator.",
    "warning.offline_failed": "La préparation hors ligne s’est arrêtée : {reason}\nVérifiez la connexion dans les paramètres de Variator.",
})

_RU.update({
    "notice.live_failed_detail": "{reason}\nПроверьте подключение в настройках Variator.",
    "warning.offline_failed": "Офлайн-подготовка остановлена: {reason}\nПроверьте подключение в настройках Variator.",
})


_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": _EN,
    "de": _DE,
    "es": _ES,
    "fr": _FR,
    "ru": _RU,
}

_ALIASES: dict[str, str] = {
    "english": "en", "en": "en",
    "deutsch": "de", "german": "de", "de": "de",
    "español": "es", "espanol": "es", "spanish": "es", "es": "es",
    "français": "fr", "francais": "fr", "french": "fr", "fr": "fr",
    "русский": "ru", "russian": "ru", "ru": "ru",
}


def normalize_ui_language(value: Any) -> str:
    """Return ``auto`` or a supported two-letter language preference."""

    if value is None:
        return "auto"
    raw = str(value).strip().lower().replace("_", "-")
    if not raw or raw in {"auto", "automatic", "anki"}:
        return "auto"
    direct = _ALIASES.get(raw)
    if direct:
        return direct
    base = raw.split("-", 1)[0]
    return _ALIASES.get(base, "auto")


def _mapping_value(container: Any, key: str) -> Any:
    if container is None:
        return None
    try:
        if hasattr(container, "get"):
            return container.get(key)
        return container[key]
    except Exception:
        return None


def _detected_language(value: Any) -> str | None:
    """Resolve an explicit locale, using English for unsupported languages."""

    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalised = normalize_ui_language(raw)
    if normalised != "auto":
        return normalised
    if raw.casefold() in {"auto", "automatic", "anki"}:
        return None
    # Anki has an explicit interface language, but Variator has no translation
    # for it yet. English is the predictable product fallback; silently using
    # the operating-system language would make the add-on differ from Anki.
    return "en"


def detect_anki_language(mw: Any = None) -> str:
    """Detect a supported language from Anki, falling back to English."""

    if mw is None:
        try:
            from aqt import mw as anki_main_window

            mw = anki_main_window
        except Exception:
            mw = None

    try:
        from anki import lang as anki_lang

        candidate = getattr(anki_lang, "current_lang", None)
        if callable(candidate):
            candidate = candidate()
        detected = _detected_language(candidate)
        if detected:
            return detected
    except Exception:
        pass

    pm = getattr(mw, "pm", None)
    for container_name in ("meta", "profile"):
        container = getattr(pm, container_name, None)
        for key in ("defaultLang", "language", "lang", "locale"):
            candidate = _mapping_value(container, key)
            detected = _detected_language(candidate)
            if detected:
                return detected

    try:
        from aqt.qt import QLocale

        for locale in (QLocale.system(), QLocale()):
            detected = _detected_language(locale.name())
            if detected:
                return detected
    except Exception:
        pass
    return "en"


def set_ui_language(preference: Any = "auto", mw: Any = None) -> str:
    """Activate a manual language or Anki's current interface language."""

    global _current_language
    normalised = normalize_ui_language(preference)
    _current_language = (
        detect_anki_language(mw) if normalised == "auto" else normalised
    )
    if _current_language not in SUPPORTED_UI_LANGUAGES:
        _current_language = "en"
    return _current_language


def current_ui_language() -> str:
    """Return the active resolved language code."""

    return _current_language


def tr(key: str, **kwargs: Any) -> str:
    """Translate ``key`` and safely interpolate named placeholders."""

    text = _TRANSLATIONS.get(_current_language, _EN).get(key, _EN.get(key, key))
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text


def language_options() -> tuple[tuple[str, str], ...]:
    """Return preference values and concise labels for the settings combo."""

    return (
        ("auto", tr("language.auto")),
        ("en", "English"),
        ("de", "Deutsch"),
        ("es", "Español"),
        ("fr", "Français"),
        ("ru", "Русский"),
    )


__all__ = [
    "SUPPORTED_UI_LANGUAGES",
    "current_ui_language",
    "detect_anki_language",
    "language_options",
    "normalize_ui_language",
    "set_ui_language",
    "tr",
]
