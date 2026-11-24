# Variator

Variator is an Anki Desktop add-on that prepares alternative wording for the
cards you are about to review. It keeps the expected answer and scheduling
intact. You can reveal the original question at any time during review.

Variator requires Anki Desktop 24.11 or newer and an API key from OpenAI,
Google Gemini, Anthropic Claude, or xAI Grok. Its interface supports English,
German, Spanish, French, and Russian.

[User guide and privacy](work/fragevariator/README.md) ·
[Changelog](work/fragevariator/CHANGELOG.md)

## Install

Open the built `.ankiaddon` file in Anki, then restart Anki. Open
**Variator → Set up connection…** to choose a provider and give permission
to send card contents.

## Develop

From the repository root with Python 3.10 or newer:

```sh
python -B -m unittest discover -s work/tests -t work
```

The tests use synthetic cards and provider responses. They run without Anki or
an API key. The optional reviewer layout test uses Node.js, Playwright with
Chromium, and the path to Anki's bundled web CSS:

```sh
node work/tests/render_reviewer_bar.cjs --css-dir "<Anki web CSS folder>"
```

## Build

Run these commands from the repository root with PowerShell 7:

```powershell
pwsh -File work/build_package.ps1
pwsh -File work/verify_package.ps1
```

The build reads the version from `work/fragevariator/manifest.json` and writes
the installable package to `outputs/Variator-<version>.ankiaddon`.

Variator is distributed under the [MIT License](LICENSE).
