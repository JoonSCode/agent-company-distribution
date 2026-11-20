"""Migrate the known Codex startup settings while preserving unrelated TOML."""
import os
import re
import stat
import subprocess
import tempfile
import tomllib
from pathlib import Path


def migrate(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise SystemExit("Expected a regular config.toml")
    mode = stat.S_IMODE(path.stat().st_mode)
    original = path.read_bytes()
    source = original.decode()
    expected = tomllib.loads(source)
    features = expected.get("features", {})
    catalog = subprocess.check_output(["codex", "features", "list"], text=True)
    def update_assignment(key, value, table, replacement=None):
        nonlocal source
        if replacement is None:
            del table[key]
        else:
            table[key] = True
        # Match a single physical assignment, then let TOML establish its scope.
        # Another table or a multiline string can contain the same text.
        pattern = rf'(?m)^[ \t]*{key}[ \t]*=[ \t]*(?:{value})[ \t]*(?:#[^\r\n]*)?(?:\r?\n|$)'
        for match in re.finditer(pattern, source):
            new_line = "" if replacement is None else match.group().replace("false", replacement, 1)
            candidate = source[:match.start()] + new_line + source[match.end():]
            try:
                parsed = tomllib.loads(candidate)
            except tomllib.TOMLDecodeError:
                continue
            if parsed == expected:
                source = candidate
                return
        raise SystemExit(f"Unrecognized layout for {key}; config preserved")

    if features.get("multi_agent") is True and re.search(r"^multi_agent\s+deprecated\s+true$", catalog, re.M):
        update_assignment("multi_agent", "true", features)
    if isinstance(features.get("child_agents_md"), bool) and not re.search(r"^child_agents_md\s+", catalog, re.M):
        version = subprocess.check_output(["codex", "--version"], text=True).strip()
        if version == "codex-cli 0.171.0":
            update_assignment("child_agents_md", "true|false", features)
    if expected.get("network_access") == "enabled" and expected.get("sandbox_mode") == "danger-full-access":
        update_assignment("network_access", """["']enabled["']""", expected)
    if features.get("chronicle") and not expected.get("suppress_unstable_features_warning"):
        if "suppress_unstable_features_warning" in expected:
            update_assignment("suppress_unstable_features_warning", "false", expected, "true")
        else:
            newline = "\r\n" if "\r\n" in source else "\n"
            source = "suppress_unstable_features_warning = true" + newline + source
            expected["suppress_unstable_features_warning"] = True
    if tomllib.loads(source) != expected:
        raise SystemExit("Unexpected TOML layout; config preserved")
    if original == source.encode():
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix="config-before-warnings-", delete=False) as backup:
        backup.write(original)
        print(f"Backup: {backup.name}")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
        os.fchmod(target.fileno(), mode)
        target.write(source.encode())
    temporary = Path(target.name)
    try:
        if path.read_bytes() != original:
            raise SystemExit("Config changed during migration")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    migrate(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml")
