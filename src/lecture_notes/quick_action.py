"""Install the Finder Quick Actions (one per note mode) into ~/Library/Services."""

from __future__ import annotations

import plistlib
import re
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path

from .config import LOG_DIR
from .modes import MODES, NoteMode

SERVICES_DIR = Path.home() / "Library" / "Services"
QUICK_ACTION_LOG = LOG_DIR / "quick-action.log"
ALERT_TITLE = "Notatki — błąd"

# Content types the action is offered for. .srt and .mkv have no system-declared
# type on a stock macOS, so their dynamic UTIs (derived from the extension) are listed.
FILE_TYPES = [
    "public.audiovisual-content",  # audio and video
    "public.text",                 # .txt
    "dyn.ah62d4rv4ge81g6xy",       # .srt
    "dyn.ah62d4rv4ge804450",       # .mkv
    "org.matroska.mkv",            # .mkv when VLC/IINA declares it
]

# Automator does not inherit the shell PATH, so everything uses full paths.
SHELL_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def mode_args(mode: NoteMode) -> list[str]:
    return [] if mode.name == "lecture" else ["--mode", mode.name]


# zsh script of the "Run Shell Script" action. A Quick Action has no terminal, so
# nothing may fail silently:
# * output goes to quick-action.log instead of /dev/null,
# * lecture-notes --quick-action reports its own errors (alert + notification + log)
#   and then exits 0, so a non-zero exit means it could not start or crashed; the
#   script then shows an alert with the end of the log,
# * a missing program or an empty file list is reported the same way.
# The script itself always exits 0: a non-zero exit would only add Finder's generic
# "action failed" alert. Alerts, unlike notifications, need no permission.
_SCRIPT = r"""export PATH="@PATH@"
exe=@EXE@
log=@LOG@
mkdir -p "$(dirname "$log")"
alert() {
  /usr/bin/osascript -e 'on run argv' \
    -e 'display alert (item 1 of argv) message (item 2 of argv) as critical' \
    -e 'end run' @TITLE@ "$1" >/dev/null 2>&1
}
printf '\n=== %s, plików: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$#" >>"$log"
if [[ ! -x "$exe" ]]; then
  printf 'Nie znaleziono %s\n' "$exe" >>"$log"
  alert "Nie znaleziono programu lecture-notes:
$exe

Zainstaluj go ponownie (pipx install …) i uruchom: lecture-notes install-quick-action"
  exit 0
fi
if (( $# == 0 )); then
  printf 'Finder nie przekazał plików\n' >>"$log"
  alert "Finder nie przekazał żadnych plików do szybkiej czynności."
  exit 0
fi
"$exe" @ARGS@ "$@" >>"$log" 2>&1
code=$?
if (( code != 0 )); then
  alert "Program lecture-notes zakończył się błędem (kod $code):

$(tail -n 8 "$log")

Pełny log: $log"
fi
exit 0
"""


def shell_command(executable: Path, args: list[str] | None = None, log_file: Path = QUICK_ACTION_LOG) -> str:
    replacements = {
        "@PATH@": SHELL_PATH,
        "@EXE@": shlex.quote(str(executable)),
        "@LOG@": shlex.quote(str(log_file)),
        "@TITLE@": shlex.quote(ALERT_TITLE),
        "@ARGS@": shlex.join(["--quick-action", *(args or [])]),
    }
    # one pass, so a value containing a marker is never substituted again
    return re.sub(r"@[A-Z]+@", lambda m: replacements[m.group(0)], _SCRIPT)


def info_plist(name: str) -> dict:
    return {
        "NSServices": [{
            "NSBackgroundColorName": "background",
            "NSIconName": "NSActionTemplate",
            "NSMenuItem": {"default": name},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": FILE_TYPES,
        }]
    }


def _argument(name: str, default, index: int) -> dict:
    return {"default value": default, "name": name, "required": "0", "type": "0", "uuid": str(index)}


def document_wflow(executable: Path, args: list[str] | None = None) -> dict:
    """Same structure Automator writes for a Quick Action with one "Run Shell Script"
    action (input: files and folders in Finder, passed as arguments)."""
    command = shell_command(executable, args)
    arguments = [
        ("inputMethod", 0),
        ("CheckedForUserDefaultShell", False),
        ("source", ""),
        ("COMMAND_STRING", ""),
        ("shell", "/bin/sh"),
    ]
    return {
        "AMApplicationBuild": "523",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{
            "action": {
                # Run Shell Script accepts strings; Automator converts the Finder
                # items to their POSIX paths
                "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
                "AMActionVersion": "2.0.3",
                "AMApplication": ["Automator"],
                "AMParameterProperties": {
                    "COMMAND_STRING": {}, "CheckedForUserDefaultShell": {},
                    "inputMethod": {}, "shell": {}, "source": {},
                },
                "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
                "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
                "ActionName": "Run Shell Script",
                "ActionParameters": {
                    "COMMAND_STRING": command,
                    "CheckedForUserDefaultShell": True,
                    "inputMethod": 1,  # pass input as arguments ("$@")
                    "shell": "/bin/zsh",
                    "source": "",
                },
                "BundleIdentifier": "com.apple.RunShellScript",
                "CFBundleVersion": "2.0.3",
                "CanShowSelectedItemsWhenRun": False,
                "CanShowWhenRun": True,
                "Category": ["AMCategoryUtilities"],
                "Class Name": "RunShellScriptAction",
                "InputUUID": str(uuid.uuid4()).upper(),
                "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
                "OutputUUID": str(uuid.uuid4()).upper(),
                "UUID": str(uuid.uuid4()).upper(),
                "UnlocalizedApplications": ["Automator"],
                "arguments": {str(i): _argument(name, default, i) for i, (name, default) in enumerate(arguments)},
                "isViewVisible": 1,
                "location": "309.000000:253.000000",
                "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
            },
            "isViewVisible": 1,
        }],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDsByPath": {},
            "applicationPaths": [],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": False,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "systemImageName": "NSActionTemplate",
            "useAutomaticInputType": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }


def workflow_path(name: str, services_dir: Path = SERVICES_DIR) -> Path:
    return services_dir / f"{name}.workflow"


def install(executable: Path, services_dir: Path = SERVICES_DIR) -> list[Path]:
    """Install one Quick Action per note mode; returns the bundle paths."""
    targets = []
    for mode in MODES.values():
        target = workflow_path(mode.quick_action, services_dir)
        if target.exists():
            shutil.rmtree(target)  # our own bundle; reinstall replaces it
        contents = target / "Contents"
        contents.mkdir(parents=True)
        with (contents / "Info.plist").open("wb") as f:
            plistlib.dump(info_plist(mode.quick_action), f)
        with (contents / "document.wflow").open("wb") as f:
            plistlib.dump(document_wflow(executable, mode_args(mode)), f)
        targets.append(target)
    _refresh_services()
    return targets


def uninstall(services_dir: Path = SERVICES_DIR) -> int:
    """Remove all Quick Actions of this program; returns how many were removed."""
    removed = 0
    for mode in MODES.values():
        target = workflow_path(mode.quick_action, services_dir)
        if target.exists():
            shutil.rmtree(target)
            removed += 1
    if removed:
        _refresh_services()
    return removed


def _refresh_services() -> None:
    pbs = Path("/System/Library/CoreServices/pbs")
    if pbs.exists():
        subprocess.run([str(pbs), "-update"], check=False, capture_output=True)
