#!/usr/bin/env python3
"""Register separately installed Tomacco 1.0.0 x86_64; check binaries without installing or starting them."""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

REVISION = "84f877eb34fb202384010afb5f54c0da7fea892f"
BINARIES = {
    "tomacco": "82001a0e863f5ab7f08a974836409ba99e198b7634965a09eb6685a97055bcba",
    "tomaccoctl": "c9ddf25e5d3ddf8fbdd8d475efade95bdf817e6b140eade4f891d609d63295d6",
}


def locations():
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return (config / "omarchy-apple-dev/tomacco.json",
            data / "applications/omarchy-apple-dev-tomacco.desktop")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def desktop_identity(path):
    info = path.stat()
    return {"device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns, "sha256": digest(path)}


def atomic_write(path, text, mode):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), mode)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate(directory):
    directory = Path(directory).resolve(strict=True)
    for name, expected in BINARIES.items():
        binary = directory / name
        if not binary.is_file() or not os.access(binary, os.X_OK) or digest(binary) != expected:
            raise ValueError(f"{binary} is not the evaluated Tomacco 1.0.0 x86_64 binary")
    return directory


def registration():
    state, _ = locations()
    if state.is_symlink():
        raise ValueError(f"Registration is not an owned regular file: {state}")
    if not state.exists():
        return None
    value = json.loads(state.read_text())
    if (not isinstance(value, dict) or value.get("release") != REVISION
            or not isinstance(value.get("directory"), str)
            or not isinstance(value.get("desktop_sha256"), str)
            or not isinstance(value.get("path"), str)
            or (value.get("previous_desktop_file") is not None
                and not isinstance(value["previous_desktop_file"], dict))):
        raise ValueError(f"Registration is not owned by this frontend: {state}")
    return value


def check_desktop(value):
    _, desktop = locations()
    linked = desktop.is_symlink()
    identity = desktop_identity(desktop) if not linked and desktop.exists() else None
    if linked or (identity is not None and
                  (value is None or (identity["sha256"] != value["desktop_sha256"]
                                     and identity != value.get("previous_desktop_file")))):
        raise ValueError(f"Desktop entry is not owned or has changed; preserving {desktop}")
    return identity


def desktop_argument(value):
    """Desktop files decode string escapes before parsing Exec arguments."""
    value = str(value).replace("%", "%%")
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    if "\n" in value or "\r" in value:
        raise ValueError("Desktop command paths must not contain newlines")
    return ('"' + value + '"').replace("\\", "\\\\")


def enable(directory):
    directory = validate(directory)
    current = registration()
    previous_desktop = check_desktop(current)
    state, desktop = locations()
    command = " ".join(desktop_argument(p) for p in (sys.executable, Path(__file__).resolve(), "launch"))
    entry = ("[Desktop Entry]\nType=Application\nName=iOS development (Tomacco)\n"
             f"Exec={command}\nTerminal=false\nCategories=Development;\n")
    value = {"release": REVISION, "directory": str(directory), "path": os.environ.get("PATH", ""),
             "desktop_sha256": hashlib.sha256(entry.encode()).hexdigest(),
             "previous_desktop_file": previous_desktop}
    state.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(state, json.dumps(value, indent=2) + "\n", 0o600)
    atomic_write(desktop, entry, 0o644)
    return {"enabled": True, "release": REVISION, "desktop": str(desktop)}


def disable():
    current = registration()
    check_desktop(current)
    state, desktop = locations()
    if current is not None:
        desktop.unlink(missing_ok=True)
        state.unlink()
    return {"enabled": False}


def launch():
    current = registration()
    if current is None:
        raise ValueError("Tomacco frontend is not enabled")
    directory = validate(current["directory"])
    os.environ["PATH"] = current["path"]
    os.execv(str(directory / "tomacco"), [str(directory / "tomacco")])


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"Evaluated source: {REVISION}. No download, bootstrap, or Apple sign-in.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("disable")
    commands.add_parser("launch")
    commands.add_parser("enable", help="Register the evaluated, separately installed release").add_argument(
        "directory", type=Path, help="Existing installation containing both evaluated tomacco and tomaccoctl binaries")
    args = parser.parse_args()
    try:
        if args.command == "enable":
            result = enable(args.directory)
        elif args.command == "disable":
            result = disable()
        elif args.command == "launch":
            launch()
            return
        else:
            current = registration()
            if current is not None:
                validate(current["directory"])
                check_desktop(current)
            result = {"enabled": current is not None, "registration": current}
        print(json.dumps(result))
    except (OSError, ValueError) as error:
        parser.exit(1, f"tomacco-frontend: {error}\n")


if __name__ == "__main__":
    main()
