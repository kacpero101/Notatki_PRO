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


_ALERT_SCRIPT = """
on run argv
    display alert (item 2 of argv) message (item 1 of argv) as critical giving up after 3600
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


def alert(message: str, title: str = "Notatki — błąd") -> None:
    """Modal alert; waits until it is dismissed (gives up after an hour).

    Notifications from osascript are silently dropped unless Script Editor may send
    notifications, so errors in a Finder Quick Action are also shown this way.
    """
    args = ["/usr/bin/osascript", "-e", _ALERT_SCRIPT, message[:2000], title]
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=3700)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Alert failed: %s", e)
        return
    if result.returncode != 0:
        log.warning("Alert failed: %s", result.stderr.strip())
