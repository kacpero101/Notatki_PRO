"""Command line entry point: ``lecture-notes <files...>``, ``setup``, ``install-quick-action``."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__
from .config import CONFIG_PATH, LOG_DIR, load_config, write_default_config
from .llm import LLMError
from .notify import notify
from .pipeline import UserError, process_file

log = logging.getLogger("lecture_notes")

COMMANDS = {"setup", "install-quick-action", "uninstall-quick-action"}


def setup_logging(verbose: bool) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "lecture-notes.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(process)d] %(name)s: %(message)s"))
    root.addHandler(fh)
    if verbose:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(sh)
    # HTTP client libraries stay quiet; request headers (API key) are never logged
    for name in ("httpx", "httpcore", "anthropic", "huggingface_hub", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return log_file


def _prepare_environment(config: dict) -> None:
    """Finder/Automator runs with a minimal PATH; mlx-whisper calls `ffmpeg` by name."""
    extra = [str(Path(p).parent) for p in (config.get("paths") or {}).values() if p]
    extra += ["/opt/homebrew/bin", "/usr/local/bin"]
    current = os.environ.get("PATH", "/usr/bin:/bin")
    os.environ["PATH"] = os.pathsep.join(dict.fromkeys(extra + current.split(os.pathsep)))
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# ------------------------------------------------------------------- process

def run_files(files: list[str], model: str | None, use_notifications: bool, verbose: bool) -> int:
    log_file = setup_logging(verbose)
    say = notify if use_notifications else (lambda *a, **k: None)
    try:
        config = load_config()
    except Exception as e:  # broken TOML etc.
        log.exception("Config error")
        say(f"Błąd konfiguracji: {e}", title="Notatki — błąd", sound="Basso")
        print(f"Błąd konfiguracji ({CONFIG_PATH}): {e}", file=sys.stderr)
        return 2
    if model:
        config["llm"]["model"] = model
    _prepare_environment(config)

    failures = 0
    for i, name in enumerate(files, 1):
        path = Path(name)
        counter = f" ({i}/{len(files)})" if len(files) > 1 else ""
        say(f"Przetwarzam{counter}: {path.name}", title="Notatki z wykładu")
        print(f"→ {path.name}")
        log.info("Processing %s (model=%s)", path, config["llm"]["model"])
        try:
            result = process_file(path, config)
        except (UserError, LLMError) as e:
            failures += 1
            log.error("%s: %s", path.name, e, exc_info=True)
            say(f"{path.name}: {e}", title="Notatki — błąd", sound="Basso")
            print(f"  ✗ {e}", file=sys.stderr)
            continue
        except Exception as e:
            failures += 1
            log.exception("Unexpected error for %s", path)
            say(f"{path.name}: nieoczekiwany błąd ({type(e).__name__}). Szczegóły w logu.",
                title="Notatki — błąd", sound="Basso")
            print(f"  ✗ {type(e).__name__}: {e} (log: {log_file})", file=sys.stderr)
            continue
        say(f"Gotowe: {result.notes_path.name}\nKoszt API {result.cost_text}",
            title="Notatki z wykładu", sound="Glass")
        print(f"  ✓ {result.notes_path}")
        if result.transcript_paths:
            print(f"  ✓ {result.transcript_paths[0].name}, {result.transcript_paths[1].name}")
        print(f"  koszt API {result.cost_text}")
    if failures:
        print(f"Szczegóły błędów: {log_file}", file=sys.stderr)
    return 1 if failures else 0


# --------------------------------------------------------------------- setup

def run_setup() -> int:
    from .keychain import get_api_key, set_api_key

    print(f"lecture-notes {__version__} — konfiguracja\n")
    if write_default_config():
        print(f"Utworzono plik konfiguracji: {CONFIG_PATH}")
    else:
        print(f"Plik konfiguracji już istnieje: {CONFIG_PATH}")
    config = load_config()

    existing = get_api_key("anthropic")
    replace = True
    if existing:
        answer = input("Klucz API Anthropic jest już zapisany. Zastąpić? [t/N] ").strip().lower()
        replace = answer in ("t", "tak", "y", "yes")
    if replace:
        key = getpass.getpass("Wklej klucz API Anthropic (sk-ant-…, nie będzie widoczny): ").strip()
        if not key:
            print("Nie podano klucza — przerwano.")
            return 1
        if not key.startswith("sk-ant-"):
            print("Uwaga: klucz nie zaczyna się od 'sk-ant-'. Zapisuję mimo to.")
        set_api_key("anthropic", key)
        print("Klucz zapisany w Pęku kluczy macOS (usługa: lecture-notes).")

    ok = _verify_key(config)
    for name, p in (config.get("paths") or {}).items():
        if not Path(p).exists():
            ok = False
            print(f"✗ Nie znaleziono {name}: {p} — zainstaluj (brew install ffmpeg) lub popraw config.toml.")
    print("\nDalej: `lecture-notes install-quick-action`, potem prawy klik na nagraniu → Szybkie czynności → Zrób notatki.")
    return 0 if ok else 1


def _verify_key(config: dict) -> bool:
    import anthropic

    from .keychain import get_api_key

    model = config["llm"]["model"]
    try:
        anthropic.Anthropic(api_key=get_api_key("anthropic"), max_retries=1).models.retrieve(model)
    except anthropic.AuthenticationError:
        print("✗ Klucz API odrzucony przez Anthropic — uruchom setup ponownie.")
        return False
    except anthropic.NotFoundError:
        print(f"✗ Klucz działa, ale model {model} jest niedostępny — sprawdź config.toml.")
        return False
    except anthropic.APIError as e:
        print(f"? Nie udało się sprawdzić klucza ({type(e).__name__}). Spróbuj później.")
        return False
    print(f"✓ Klucz API działa, model {model} dostępny.")
    return True


# --------------------------------------------------------------------- quick action

def run_install_quick_action() -> int:
    from .quick_action import install

    exe = Path(sys.argv[0]).absolute()
    if exe.name != "lecture-notes":
        exe = Path.home() / ".local" / "bin" / "lecture-notes"
    if not exe.exists():
        print(f"Nie znaleziono {exe}. Zainstaluj najpierw program przez pipx.", file=sys.stderr)
        return 1
    target = install(exe)
    print(f"✓ Zainstalowano szybką czynność: {target}")
    print(f"  Uruchamia: {exe}")
    print("  W Finderze: prawy klik na pliku → Szybkie czynności → Zrób notatki.")
    print("  Jeśli jej nie widać: Ustawienia systemowe → Ogólne → Rozszerzenia logowania i rozszerzenia")
    print("  → Finder → włącz „Zrób notatki”.")
    return 0


def run_uninstall_quick_action() -> int:
    from .quick_action import uninstall

    print("✓ Usunięto szybką czynność." if uninstall() else "Szybka czynność nie była zainstalowana.")
    return 0


# ---------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in COMMANDS and not Path(argv[0]).exists():
        return {
            "setup": run_setup,
            "install-quick-action": run_install_quick_action,
            "uninstall-quick-action": run_uninstall_quick_action,
        }[argv[0]]()

    parser = argparse.ArgumentParser(
        prog="lecture-notes",
        description="Transkrypcja wykładu i notatki .docx. Polecenia: setup, install-quick-action, "
                    "uninstall-quick-action.",
    )
    parser.add_argument("files", nargs="+", help="nagrania (m4a, mp3, mp4, mkv, …) lub transkrypcje (.txt, .srt)")
    parser.add_argument("--model", help="nadpisz model z config.toml (np. claude-haiku-5-5)")
    parser.add_argument("--no-notify", action="store_true", help="bez powiadomień macOS")
    parser.add_argument("-q", "--quiet", action="store_true", help="bez logów w terminalu")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    verbose = sys.stderr.isatty() and not args.quiet
    return run_files(args.files, args.model, not args.no_notify, verbose)


if __name__ == "__main__":
    sys.exit(main())
