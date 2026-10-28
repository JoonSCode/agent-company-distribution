#!/usr/bin/env python3
"""Read-only, portable comparison of accepted Orca source contracts (stdlib only)."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
import sys
from urllib.parse import unquote, urlsplit

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

BASELINE = "company-orchestration-baseline/v1"
OBSERVATION = "company-orchestration-observation/v1"
REFERENCES = frozenset(f"references/{name}.md" for name in (
    "coordinator-loop", "messaging-and-gates", "recovery-and-cleanup",
    "worker-contract", "placement-and-remote", "low-level-topology",
    "legacy-contract-migration"))
EXITS = {"baseline_match": 0, "formatting_only": 0, "valid": 0,
         "observed": 0, "review_required": 1, "unverifiable": 2, "invalid": 3}
TIMEOUT = 20


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def string(value, label):
    require(isinstance(value, str) and bool(value.strip()) and "\x00" not in value,
            f"{label} must be a nonempty string")
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(value, label="sha256"):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            f"{label} must be a lowercase SHA-256")
    return value


def read(root, relative):
    string(relative, "path")
    path = PurePosixPath(relative)
    require(not path.is_absolute() and "\\" not in relative
            and all(part not in ("", ".", "..") for part in relative.split("/")),
            f"unsafe path: {relative}")
    candidate = root
    for part in path.parts:
        candidate = candidate / part
        require(not candidate.is_symlink(), f"symlink forbidden: {relative}")
    require(candidate.is_file() and stat.S_ISREG(candidate.stat().st_mode),
            f"regular file missing: {relative}")
    require(candidate.resolve().is_relative_to(root.resolve()), f"path escapes package: {relative}")
    return candidate.read_bytes()


def decode(data, label):
    try:
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, f"duplicate JSON key in {label}: {key}")
                result[key] = value
            return result
        result = json.loads(data, object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        raise Invalid(f"invalid JSON in {label}: {exc}") from exc
    require(isinstance(result, dict), f"{label} must be an object")
    return result


def utf8(data, label):
    try:
        return data.decode("utf-8")
    except UnicodeError as exc:
        raise Invalid(f"{label} is not UTF-8") from exc


def binding(root, item):
    require(isinstance(item, dict), "file binding must be an object")
    data = read(root, item.get("path"))
    require(digest(data) == sha(item.get("sha256")), f"SHA-256 mismatch: {item['path']}")
    return data


def policy_dependencies(root, source, data, bound_paths):
    """Check the simple inline file links used as active package dependencies."""
    for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]*)\)", utf8(data, source)):
        require(target and not any(c.isspace() for c in target),
                f"use a simple inline dependency link in {source}: {target}")
        url = urlsplit(target)
        if url.scheme in ("https", "http") and url.netloc:
            continue  # Evidence URL, not an executable local dependency.
        require(not url.scheme and not url.netloc,
                f"external file dependency in {source}: {target}")
        if not url.path:
            require(bool(url.fragment) and not url.query, f"empty dependency in {source}")
            continue
        path = unquote(url.path)
        require(not PurePosixPath(path).is_absolute() and "\\" not in path and not url.query,
                f"unsafe dependency in {source}: {target}")
        relative = posixpath.normpath(str(PurePosixPath(source).parent / path))
        read(root, relative)  # Enforces package containment and rejects symlinks.
        require(relative in bound_paths, f"unbound policy dependency in {source}: {relative}")


def load_package(root):
    require(not root.is_symlink(), "package directory is a symlink")
    baseline = decode(read(root, "references/upstream/baseline.json"), "baseline")
    require(baseline.get("schema_version") == BASELINE, "unsupported baseline schema")
    string(baseline.get("revision"), "revision")
    string(baseline.get("verification_scope"), "verification_scope")
    upstream = baseline.get("upstream")
    require(isinstance(upstream, dict), "upstream must be an object")
    string(upstream.get("source_url"), "source_url")
    require(upstream.get("skill_path") == "skills/orchestration/SKILL.md", "unexpected upstream skill_path")
    string(upstream.get("app_version"), "app_version")
    stub = binding(root, upstream.get("stub"))
    utf8(stub, "discovery stub")
    blob = hashlib.sha1(b"blob " + str(len(stub)).encode() + b"\0" + stub).digest()
    tree = b"100644 SKILL.md\0" + blob
    identity = hashlib.sha1(b"tree " + str(len(tree)).encode() + b"\0" + tree).hexdigest()
    require(upstream.get("folder_hash") == identity, "upstream single-SKILL.md Git tree hash mismatch")
    docs = upstream.get("documents")
    require(isinstance(docs, list) and docs, "documents must be a nonempty list")
    ids, references, paths = set(), set(), {upstream["stub"]["path"]}
    for item in docs:
        require(isinstance(item, dict), "document must be an object")
        name = string(item.get("id"), "document id")
        require(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name), "unsafe document id")
        ref = item.get("reference")
        require(ref is None or (isinstance(ref, str) and ref in REFERENCES), "unsupported reference")
        require(name not in ids and ref not in references, "duplicate document id/reference")
        require(item.get("path") not in paths, "duplicate bound path")
        ids.add(name)
        references.add(ref)
        paths.add(item.get("path"))
        utf8(binding(root, item), name)
    require(None in references, "kernel document missing")
    caps = baseline.get("required_capabilities")
    require(isinstance(caps, dict) and caps, "required_capabilities must be a nonempty object")
    for scope, names in caps.items():
        string(scope, "capability scope")
        require(isinstance(names, list) and names, "required capabilities must be a nonempty list")
        for name in names:
            string(name, "capability name")
        require(len(names) == len(set(names)), "duplicate required capability")
    policy = baseline.get("policy_files")
    require(isinstance(policy, list) and policy, "policy_files must be a nonempty list")
    active_documents = {}
    for item in policy:
        data = binding(root, item)
        require(item["path"] not in paths, "duplicate bound path")
        paths.add(item["path"])
        if item["path"].endswith(".md"):
            active_documents[item["path"]] = data
    require("SKILL.md" in active_documents, "active SKILL.md policy binding missing")
    for source, data in active_documents.items():
        policy_dependencies(root, source, data, paths)
    adoptions = baseline.get("adoptions")
    require(isinstance(adoptions, list), "adoptions must be a list")
    for item in adoptions:
        require(isinstance(item, dict), "adoption must be an object")
        for key in ("source", "disposition", "reason"):
            string(item.get(key), f"adoption {key}")
        if "sha256" in item:
            sha(item["sha256"])
    return baseline


def command_args(doc=None):
    if doc is None:
        return ["status", "--json"]
    args = ["skills", "get", "orchestration"]
    if doc["reference"] is not None:
        args += ["--reference", doc["reference"]]
    return args


def resolve_orca(explicit):
    if explicit is not None:
        return string(explicit, "--orca")
    if "ORCA_CLI_COMMAND" in os.environ:
        return string(os.environ["ORCA_CLI_COMMAND"], "ORCA_CLI_COMMAND")
    if os.environ.get("ORCA_DEV_REPO_ROOT"):
        return "orca-dev"
    # Orca exports this handle for managed terminals; outside them bare `orca`
    # on Linux can be the GNOME screen reader.
    managed = bool(os.environ.get("ORCA_TERMINAL_HANDLE"))
    return "orca-ide" if sys.platform.startswith("linux") and not managed else "orca"


def capture(executable, args, output, filename):
    error, code, stdout, stderr = None, None, b"", b""
    try:
        receipt = subprocess.run([executable, *args], capture_output=True, timeout=TIMEOUT, check=False)
        code, stdout, stderr = receipt.returncode, receipt.stdout, receipt.stderr
        if code != 0:
            error = "command_failed"
    except subprocess.TimeoutExpired as exc:
        error, stdout, stderr = "timeout", exc.stdout or b"", exc.stderr or b""
    except OSError as exc:
        error, stderr = "executable_unavailable", str(exc).encode()
    (output / filename).write_bytes(stdout)
    (output / (filename + ".stderr")).write_bytes(stderr)
    return {"argv": [executable, *args], "returncode": code, "error": error,
            "path": filename, "sha256": digest(stdout),
            "stderr": {"path": filename + ".stderr", "sha256": digest(stderr)}}


def observe(root, baseline, output, executable):
    # A new directory is reserved atomically before executing any command.
    require(not output.is_symlink(), "observation directory is a symlink")
    require(not output.resolve().is_relative_to(root.resolve()), "observation must be outside the package")
    output.mkdir(parents=False, exist_ok=False)
    (output / "documents").mkdir()
    status = capture(executable, command_args(), output, "status.json")
    docs = []
    for doc in baseline["upstream"]["documents"]:
        docs.append({"id": doc["id"], "reference": doc["reference"],
                     **capture(executable, command_args(doc), output, f"documents/{doc['id']}.md")})
    metadata = {"schema_version": OBSERVATION, "baseline_revision": baseline["revision"],
                "executable": executable, "status": status, "documents": docs}
    (output / "observation.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    errors = [item["error"] for item in [status, *docs] if item["error"]]
    return {"status": "unverifiable" if errors else "observed", "observation": str(output),
            "errors": errors, "evidence_scope": "read-only source observation"}


def evidence(root, item, executable, args):
    require(isinstance(item, dict), "command evidence must be an object")
    require(item.get("argv") == [executable, *args], "unexpected observation command argv")
    code, error = item.get("returncode"), item.get("error")
    require(code is None or type(code) is int, "returncode must be an integer or null")
    require(error is None or error in ("command_failed", "timeout", "executable_unavailable"), "invalid command error")
    require((code == 0 and error is None) or
            (type(code) is int and code != 0 and error == "command_failed") or
            (code is None and error in ("timeout", "executable_unavailable")),
            "inconsistent command outcome")
    data = binding(root, item)
    binding(root, item.get("stderr"))
    return data, error


def runtime_status(data):
    receipt = decode(data, "runtime status")
    if "ok" in receipt:
        require(type(receipt["ok"]) is bool, "runtime ok must be boolean")
        if not receipt["ok"]:
            return None, None, "runtime_status_failed", None
        receipt = receipt.get("result")
        require(isinstance(receipt, dict), "runtime status result must be an object")
    runtime = receipt.get("runtime")
    if runtime is None:
        return None, None, "runtime_evidence_missing", None
    require(isinstance(runtime, dict), "runtime must be an object")
    reachable = runtime.get("reachable")
    if reachable is not None:
        require(type(reachable) is bool, "runtime reachable must be boolean")
    state = runtime.get("state")
    identity = runtime.get("runtimeId")
    if state is not None:
        string(state, "runtime state")
    if identity is not None:
        string(identity, "runtimeId")
    caps = runtime.get("capabilities")
    if caps is not None:
        require(isinstance(caps, list), "runtime capabilities must be a list")
        for cap in caps:
            string(cap, "runtime capability")
    version = runtime.get("appVersion")
    if version is not None:
        string(version, "runtime version")
    provenance = {key: runtime.get(key) for key in ("runtimeId", "state", "reachable")}
    if reachable is not True or state != "ready" or identity is None:
        return None, None, "runtime_unavailable_or_incomplete", provenance
    if caps is None:
        return None, None, "capabilities_missing", provenance
    if version is None:
        return caps, None, "runtime_version_missing", provenance
    return caps, version, None, provenance


def formatting(text):
    # Only trailing spaces in ordinary non-indented prose outside code fences.
    # Leading whitespace, fence content, hard breaks, tabs and blank-line counts
    # remain significant; this deliberately misses some harmless changes.
    lines, fence_marker = [], None
    for line in text.splitlines(keepends=True):
        body = line.removesuffix("\n")
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})", body)
        if fence and fence_marker is None:
            fence_marker = fence[1]
        elif fence and fence_marker is not None and fence[1][0] == fence_marker[0] and len(fence[1]) >= len(fence_marker) and not body[fence.end():].strip():
            fence_marker = None
        if (fence_marker is None and not fence and body and not body[0].isspace()
                and not body.endswith("  ") and "\\" not in body and "\t" not in body and "`" not in body):
            body = body.rstrip(" ")
        lines.append(body + ("\n" if line.endswith("\n") else ""))
    return "".join(lines)


def compare(root, baseline, observation, scope):
    require(scope in baseline["required_capabilities"], f"unknown scope: {scope}")
    require(not observation.is_symlink(), "observation directory is a symlink")
    metadata = decode(read(observation, "observation.json"), "observation")
    require(metadata.get("schema_version") == OBSERVATION, "unsupported observation schema")
    string(metadata.get("baseline_revision"), "observation baseline_revision")
    executable = string(metadata.get("executable"), "observation executable")
    observed_docs = metadata.get("documents")
    require(isinstance(observed_docs, list), "observation documents must be a list")
    expected = {doc["id"]: doc for doc in baseline["upstream"]["documents"]}
    docs, errors, changes = {}, [], []
    # Absence of an expected command is missing evidence, not positive mismatch.
    for item in observed_docs:
        require(isinstance(item, dict), "observed document must be an object")
        name = string(item.get("id"), "observed id")
        require(name in expected and name not in docs, "unknown/duplicate observed document")
        doc = expected[name]
        require(item.get("reference") == doc["reference"], "observed reference mismatch")
        data, error = evidence(observation, item, executable, command_args(doc))
        docs[name] = data
        if error:
            errors.append({"document": name, "error": error})
            continue
        text = utf8(data, name)
        if not text.strip():
            errors.append({"document": name, "error": "empty_document"})
            continue
        accepted = read(root, doc["path"])
        if data != accepted:
            original = utf8(accepted, name)
            category = "formatting_only" if formatting(original) == formatting(text) else "review_required"
            changes.append({"id": name, "baseline_sha256": doc["sha256"], "observed_sha256": digest(data),
                            "status": category, "diff": "".join(difflib.unified_diff(
                                original.splitlines(keepends=True), text.splitlines(keepends=True),
                                fromfile=f"baseline/{name}", tofile=f"observed/{name}"))})
    for missing in sorted(expected.keys() - docs.keys()):
        errors.append({"document": missing, "error": "missing_document"})
    caps, version, runtime = None, None, None
    if metadata.get("status") is None:
        errors.append({"error": "missing_runtime_status"})
    else:
        status_bytes, error = evidence(observation, metadata["status"], executable, command_args())
        if error or not status_bytes.strip():
            errors.append({"error": error or "empty_runtime_status"})
        else:
            caps, version, error, runtime = runtime_status(status_bytes)
            if error:
                errors.append({"error": error})
    missing_caps = sorted(set(baseline["required_capabilities"][scope]) - set(caps or []))
    outcome = "unverifiable" if errors else "review_required" if (missing_caps or any(
        item["status"] == "review_required" for item in changes)) else "formatting_only" if changes else "baseline_match"
    return {"status": outcome, "scope": scope, "baseline_revision": baseline["revision"],
            "observation_baseline_revision": metadata["baseline_revision"],
            "version": {"baseline": baseline["upstream"]["app_version"], "observed": version,
                        "changed": version is not None and version != baseline["upstream"]["app_version"]},
            "required_capabilities": baseline["required_capabilities"][scope],
            "missing_capabilities": missing_caps if caps is not None else [],
            "affected_scopes": [scope] if caps is not None and missing_caps else [],
            "runtime": runtime,
            "documents": changes, "errors": errors,
            "evidence_scope": "source observation; not proof of runtime behavior"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "observe", "compare"):
        command = commands.add_parser(name)
        command.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
        command.add_argument("--json", action="store_true")
        if name == "observe":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--orca")
        if name == "compare":
            command.add_argument("--observation", type=Path, required=True)
            command.add_argument("--scope", default="local_supervision")
    args = parser.parse_args(argv)
    try:
        baseline = load_package(args.package)
        if args.command == "check":
            result = {"status": "valid", "revision": baseline["revision"],
                      "evidence_scope": baseline["verification_scope"]}
        elif args.command == "observe":
            result = observe(args.package, baseline, args.output, resolve_orca(args.orca))
        else:
            result = compare(args.package, baseline, args.observation, args.scope)
    except (Invalid, OSError, TypeError, KeyError) as exc:
        result = {"status": "invalid", "errors": [str(exc)]}
    print(json.dumps(result, indent=2) if args.json else
          result["status"] + "\n" + json.dumps(result, indent=2))
    return EXITS[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
