# lecture-notes

Turn lecture recordings into study notes in Word — on a Mac, with one right-click.

`lecture-notes` transcribes a recording locally with [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
(Apple Silicon), saves the transcript as `.txt` and `.srt`, and asks an LLM (Claude by default)
to produce structured notes, which are rendered into a `.docx` file next to the recording.
The notes are in Polish; the tool is built for Polish-language lectures.

**What the notes contain**

- title (file name) and recording date
- summary of the whole lecture
- topic-by-topic notes, without digressions and repetitions
- definitions
- formulas and examples (plain-text formulas in a monospaced font, e.g. `f(x) = x^2 + 1`)
- **exam material** — what the lecturer explicitly flagged ("to będzie na kolokwium")
  kept separate from what was merely stressed or repeated, each with an `[hh:mm:ss]`
  timestamp and a short justification
- review questions
- fragments of the transcript that are probably misrecognised (terms, names, formulas)
- metadata: model, API cost, generation date

The model is instructed to use only what was said in the lecture and never to invent
timestamps; timestamps returned by the model are validated in code and dropped when the
source has none (e.g. a plain `.txt`).

## Requirements

- Mac with Apple Silicon, macOS 14+
- [Homebrew](https://brew.sh), `ffmpeg` (`brew install ffmpeg`), `pipx` (`brew install pipx`)
- Python 3.12 (`brew install python@3.12`)
- An [Anthropic API key](https://console.anthropic.com/) (paid usage, see [Costs](#costs))

## Installation

```bash
git clone https://github.com/kacpero101/Notatki_PRO.git
cd Notatki_PRO
pipx install --python /opt/homebrew/bin/python3.12 .
```

This installs the `lecture-notes` command into `~/.local/bin` (run `pipx ensurepath` once if
that directory is not on your `PATH`). The first transcription downloads the Whisper model
(~1.6 GB) into the Hugging Face cache; if you already used `mlx-community/whisper-large-v3-turbo`
before, the cached copy is reused.

To upgrade after `git pull`: `pipx install --force --python /opt/homebrew/bin/python3.12 .`

## API key and configuration

```bash
lecture-notes setup
```

`setup` creates `~/.config/lecture-notes/config.toml` (a copy of
[`config.example.toml`](config.example.toml)), asks for your Anthropic API key, stores it in
the **macOS Keychain** (service `lecture-notes`) and checks that it works. The key is never
written to files or logs. As a fallback the `ANTHROPIC_API_KEY` environment variable is used.

In `config.toml` you can change:

| Section | What |
|---|---|
| `[llm]` | `model` (`claude-sonnet-5-5` default, `claude-haiku-5-5` cheaper), `effort`, output limit, chunk size for very long lectures |
| `[whisper]` | Whisper model, language, `initial_prompt` (course vocabulary — helps with technical terms), anti-loop parameters |
| `[transcript]` | length of the timestamped blocks sent to the model (30–60 s) |
| `[paths]` | full paths to `ffmpeg` / `ffprobe` |
| `[pricing.*]` | USD per million tokens, used for the cost estimate — **update when prices change** |

## Usage from Finder (Quick Action)

```bash
lecture-notes install-quick-action      # or: ./scripts/install-quick-action.sh
```

Then right-click one or more recordings (`m4a`, `mp3`, `wav`, `mp4`, `mkv`, `mov`, …) or
transcripts (`.txt`, `.srt`) → **Quick Actions → Zrób notatki**.

You get a notification when processing starts, and another one when the notes are ready
(with the API cost) or when something failed. A one-hour lecture takes a few minutes to
transcribe on an M-series Mac; a gear icon in the menu bar shows that the action is running.

Output, next to the source file (existing files are never overwritten — a ` (2)` suffix is added):

```
Wykład 3.m4a
Wykład 3.txt                 # plain transcript
Wykład 3.srt                 # transcript with timestamps
Wykład 3 – notatki.docx      # notes
```

If the action is missing: *System Settings → General → Login Items & Extensions → Finder*
and enable “Zrób notatki”. If no notifications appear, allow notifications for
*Script Editor* in *System Settings → Notifications*. Remove the action with
`lecture-notes uninstall-quick-action`.

## Usage from the terminal

```bash
lecture-notes "Wykład 3.m4a"
lecture-notes wyklad.srt notatki.txt          # several files, processed one after another
lecture-notes --model claude-haiku-5-5 wyklad.mp4
lecture-notes --no-notify wyklad.m4a
```

Logs: `~/Library/Logs/lecture-notes/lecture-notes.log`.

## Costs

Transcription runs locally and is free. The notes cost one API call (or a few for very long
lectures, which are split into parts and merged). The cost is computed from the token usage
reported by the API and the prices in your config, and shown in the notification and in the
document.

Rough estimate for a 90-minute lecture (~35k input tokens, ~10k output tokens):

| Model | Approx. cost |
|---|---|
| `claude-sonnet-5-5` (default) | ~$0.15–0.25 |
| `claude-haiku-5-5` | ~$0.01 |

## How Whisper loops are handled

Whisper sometimes "hallucinates" on silence or noise — repeating the same sentence or
inventing subtitle credits. Two layers reduce this:

1. **Decoding**: `condition_on_previous_text = false` (a loop cannot feed itself),
   compression-ratio and log-probability thresholds with temperature fallback, and
   `hallucination_silence_threshold` to skip suspicious text in long silences.
2. **Post-processing**: phrases repeated many times within a segment are collapsed,
   segments repeating one of the previous three are dropped, known Polish subtitle-credit
   hallucinations ("Napisy stworzone przez społeczność Amara.org") and highly repetitive
   segments are removed.

## Privacy

Audio never leaves your Mac. The transcript text is sent to the configured LLM provider
(Anthropic) to generate the notes. `.gitignore` excludes recordings, transcripts, generated
documents, `.env` files and logs.

## Architecture

```
src/lecture_notes/
  cli.py            entry point: files, setup, install-quick-action
  pipeline.py       one file: transcribe → notes → .docx
  transcribe.py     mlx-whisper with anti-loop settings
  transcript.py     segments, .txt/.srt parsing and writing, loop removal, 30–60 s blocks
  notes.py          JSON schema, prompts, chunking and merging
  llm/base.py       LLMProvider interface
  llm/anthropic_provider.py
  docx_builder.py   python-docx rendering
  cost.py           cost from usage and config prices
  keychain.py       API key in the macOS Keychain
  quick_action.py   Finder Quick Action bundle
```

The model returns JSON validated against a schema (structured outputs); the document is
built in code. To add another provider (e.g. Azure OpenAI or a local model), implement
`LLMProvider.generate_json` and register it in `lecture_notes/llm/__init__.py`.

## Development

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest              # unit tests, fake LLM, no API calls
.venv/bin/pytest -m e2e       # real mlx-whisper on a synthetic recording (say -v Zosia)
```

## License

[MIT](LICENSE)

---

## Po polsku

**lecture-notes** robi notatki do nauki z nagrań wykładów. Nagranie jest transkrybowane
lokalnie na Macu (mlx-whisper), a model językowy (domyślnie Claude Sonnet) przygotowuje z
transkrypcji dokument Word: streszczenie, notatki tematyczne, definicje, wzory, sekcję
**„Na egzamin / zaliczenie”** ze znacznikami czasu (osobno to, co prowadzący powiedział
wprost, osobno to, co tylko akcentował), pytania do powtórki i listę fragmentów
transkrypcji do sprawdzenia.

Szybki start:

```bash
pipx install --python /opt/homebrew/bin/python3.12 .
lecture-notes setup                  # klucz API trafia do Pęku kluczy macOS
lecture-notes install-quick-action   # czynność „Zrób notatki” w Finderze
```

Potem: prawy klik na nagraniu lub pliku `.txt` / `.srt` → *Szybkie czynności* →
*Zrób notatki*. Powiadomienie pokaże, kiedy notatki będą gotowe i ile kosztowało wywołanie
API. Konfiguracja (model, cennik, podpowiedź słownictwa dla Whispera) jest w
`~/.config/lecture-notes/config.toml`, logi w `~/Library/Logs/lecture-notes/`.
