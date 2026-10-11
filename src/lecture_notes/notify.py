"""macOS notifications via osascript (no extra dependencies)."""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

_SCRIPT = """
on run argv
    if (count of argv) > 2 then
        display notification (item 1 of argv) with title (item 2 of argv) sound name (item 3 of argv)
    else
        display notification (item 1 of argv) with title (item 2 of argv)
    end if
end run
"""


def notify(message: str, title: str = "Notatki z wykładu", sound: str | None = None) -> None:
    # Text is passed as argv, so quotes in file names need no escaping.
    args = ["/usr/bin/osascript", "-e", _SCRIPT, message[:240], title]
    if sound:
        args.append(sound)
    try:
        subprocess.run(args, check=False, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:  # notifications are best effort
        log.warning("Notification failed: %s", e)
