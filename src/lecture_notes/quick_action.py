"""Install the Finder Quick Actions (one per note mode) into ~/Library/Services."""

from __future__ import annotations

import plistlib
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path

from .modes import MODES, NoteMode

SERVICES_DIR = Path.home() / "Library" / "Services"

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


def shell_command(executable: Path, args: list[str] | None = None) -> str:
    # Errors are reported by lecture-notes itself (notification + log); a non-zero
    # exit would make Finder show an extra generic "action failed" alert.
    return (
        f'export PATH="{SHELL_PATH}"\n'
        f'{shlex.join([str(executable), *(args or [])])} "$@" >/dev/null 2>&1\n'
        "exit 0\n"
    )


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


def document_wflow(executable: Path, args: list[str] | None = None) -> dict:
    command = shell_command(executable, args)
    return {
        "AMApplicationBuild": "523",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{
            "action": {
                "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.path"]},
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
                "arguments": {
                    "0": {"default value": 0, "name": "inputMethod", "required": "0", "type": "0", "uuid": "0"},
                    "1": {"default value": "", "name": "source", "required": "0", "type": "0", "uuid": "0"},
                    "2": {"default value": False, "name": "CheckedForUserDefaultShell", "required": "0",
                          "type": "0", "uuid": "0"},
                    "3": {"default value": "", "name": "COMMAND_STRING", "required": "0", "type": "0", "uuid": "0"},
                    "4": {"default value": "/bin/sh", "name": "shell", "required": "0", "type": "0", "uuid": "0"},
                },
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
