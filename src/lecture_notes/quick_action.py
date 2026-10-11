"""Install the Finder Quick Action "Zrób notatki" into ~/Library/Services."""

from __future__ import annotations

import plistlib
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path

ACTION_NAME = "Zrób notatki"
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


def shell_command(executable: Path) -> str:
    # Errors are reported by lecture-notes itself (notification + log); a non-zero
    # exit would make Finder show an extra generic "action failed" alert.
    return (
        f'export PATH="{SHELL_PATH}"\n'
        f'{shlex.quote(str(executable))} "$@" >/dev/null 2>&1\n'
        "exit 0\n"
    )


def info_plist() -> dict:
    return {
        "NSServices": [{
            "NSBackgroundColorName": "background",
            "NSIconName": "NSActionTemplate",
            "NSMenuItem": {"default": ACTION_NAME},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": FILE_TYPES,
        }]
    }


def document_wflow(executable: Path) -> dict:
    command = shell_command(executable)
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


def workflow_path(services_dir: Path = SERVICES_DIR) -> Path:
    return services_dir / f"{ACTION_NAME}.workflow"


def install(executable: Path, services_dir: Path = SERVICES_DIR) -> Path:
    target = workflow_path(services_dir)
    if target.exists():
        shutil.rmtree(target)  # our own bundle; reinstall replaces it
    contents = target / "Contents"
    contents.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as f:
        plistlib.dump(info_plist(), f)
    with (contents / "document.wflow").open("wb") as f:
        plistlib.dump(document_wflow(executable), f)
    _refresh_services()
    return target


def uninstall(services_dir: Path = SERVICES_DIR) -> bool:
    target = workflow_path(services_dir)
    if not target.exists():
        return False
    shutil.rmtree(target)
    _refresh_services()
    return True


def _refresh_services() -> None:
    pbs = Path("/System/Library/CoreServices/pbs")
    if pbs.exists():
        subprocess.run([str(pbs), "-update"], check=False, capture_output=True)
