#!/usr/bin/env python3
"""Explicit local Git wrapping of the existing private cache; no remote or sync."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import research_cache as cache

FORMAT = "company-knowledge-migration/v1"
RECEIPT = ".knowledge-repository.json"
HISTORY_RE = re.compile(r"^history/[a-z0-9][a-z0-9-]{0,63}/[1-9][0-9]*\.(json|md)$")
CONFLICT_RE = re.compile(r"^conflicts/[a-z0-9][a-z0-9-]{0,63}/[0-9a-f]{64}-[0-9a-f]{64}\.json$")
ORIGIN_RE = re.compile(r"^origins/([0-9a-f]{64})\.(md|json)$")
SEED_FORMAT = "company-knowledge-seed/v1"
SEED_JOURNALS = ".knowledge-seeds"
GIT_STAGE = ".knowledge-git-init"
INIT_RECEIPT = ".knowledge-init.json"


def _document(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write_control(path, value):
    body = dict(value)
    body["sha256"] = cache._digest(cache._canonical(value))
    data = _document(body)
    cache._require(len(data) <= cache.MAX_INDEX_BYTES, "too_large", "recovery evidence exceeds storage boundary")
    cache._atomic_write(path, data, 0o600)


def _read_control(path):
    value = cache._json(cache._read_file(path, cache.MAX_INDEX_BYTES), "recovery evidence")
    cache._require(isinstance(value, dict), "recovery_conflict", "recovery evidence object required")
    digest = value.pop("sha256", None)
    cache._require(cache._digest(cache._canonical(value)) == digest,
                   "recovery_conflict", "recovery evidence changed; preserve and review")
    return value


def _file_manifest(root):
    files = []
    for path in sorted(root.rglob("*")):
        cache._reject_symlink(path, "recovery metadata")
        if path.is_file():
            data = cache._read_file(path, cache.MAX_INDEX_BYTES)
            files.append({"path": path.relative_to(root).as_posix(), "sha256": cache._digest(data), "bytes": len(data)})
    return files


def _git(root, *args):
    # Inherited alternate Git directories/config and user templates must not
    # redirect this private operation or execute a user hook/filter/signing tool.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    command = ["git", "-c", "core.hooksPath=" + os.devnull, "-c", "commit.gpgsign=false",
               "-c", "init.templateDir=", "-c", "core.fsmonitor=false",
               "-c", "core.attributesFile=" + os.devnull, *args]
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=30)
    cache._require(result.returncode == 0, "git_failed", "local Git operation failed: " + args[0])
    return result.stdout.decode("utf-8").strip()


def _root(store):
    for path in (store.root, *store.root.parents):
        cache._reject_symlink(path, "knowledge ancestor")
    git = store.root / ".git"
    cache._reject_symlink(git, ".git")
    if git.exists():
        cache._require(git.is_dir(), "git_boundary", "linked worktree or alternate Git directory is not a knowledge repository")
        cache._require((git / "HEAD").is_file(), "git_boundary", "incomplete Git initialization; inspect before retry")
        for path in git.rglob("*"):
            cache._reject_symlink(path, "Git metadata")
        cache._require(not any(git.rglob("*.lock")), "git_busy", "Git writer lock exists")
        cache._require(Path(_git(store.root, "rev-parse", "--show-toplevel")).resolve() == store.root.resolve(),
                       "git_boundary", "Git root differs")
        # Refuse inherited local attributes/filters; candidates have no attributes.
        cache._require(not (git / "info/attributes").exists(), "git_boundary", "local Git attributes require separate review")
    return git


def _inventory(store):
    for folder in (store.records, store.history, store.conflicts):
        cache._reject_symlink(folder, folder.name)
    cache._require(not any(store.root.rglob(".gitattributes")), "git_boundary", "Git attributes require separate review")
    store._mutation_index()
    allowed = {"index.json"}
    for row in store._load_index():
        allowed.update(f"records/{row['id']}.{suffix}" for suffix in ("json", "md"))
    for folder in (store.history, store.conflicts):
        cache._reject_symlink(folder, folder.name)
        for path in folder.rglob("*"):
            cache._reject_symlink(path, "archive")
            if path.is_file():
                name = path.relative_to(store.root).as_posix()
                cache._require(bool(HISTORY_RE.fullmatch(name) or CONFLICT_RE.fullmatch(name)),
                               "unexpected_archive", "unknown history/conflict file; preserve and review")
                allowed.add(name)
    origins = store.root / "origins"
    if origins.exists():
        cache._reject_symlink(origins, "origins")
        for path in origins.iterdir():
            name = path.relative_to(store.root).as_posix()
            match = ORIGIN_RE.fullmatch(name)
            cache._require(match is not None, "unexpected_archive", "unknown original archive file")
            data = cache._read_file(path, cache.MAX_BYTES)
            cache._require(cache._digest(data) == match[1], "archive_conflict", "original archive hash differs")
            allowed.add(name)
    files = []
    for name in sorted(allowed):
        data = cache._read_file(store.root / name, cache.MAX_INDEX_BYTES if name == "index.json" else cache.MAX_BYTES)
        cache.safe_note(data)
        files.append({"path": name, "sha256": cache._digest(data), "bytes": len(data)})
    excluded = []
    # Only list unknown paths. Never load a transcript, media or unrelated body.
    for base, dirs, names in os.walk(store.root, followlinks=False):
        relative = Path(base).relative_to(store.root)
        dirs[:] = [name for name in dirs if not (relative == Path(".") and name in (".git", SEED_JOURNALS, GIT_STAGE))]
        for name in list(dirs):
            if (Path(base) / name).is_symlink():
                excluded.append((relative / name).as_posix())
                dirs.remove(name)
        for name in names:
            entry = (relative / name).as_posix()
            if entry not in allowed and entry not in ("lock", RECEIPT, INIT_RECEIPT):
                excluded.append(entry)
    return files, sorted(excluded)


def _plan(store):
    _root(store)
    files, excluded = _inventory(store)
    result = {"format": FORMAT, "root": str(store.root.resolve()), "files": files,
              "excluded": excluded, "privacy_review_required": True,
              "limits": "Pattern screening is incomplete; inspect curated text before applying. Originals are not rewritten."}
    result["plan_sha256"] = cache._digest(cache._canonical(result))
    return result


def plan(store):
    with store._shared():
        return _plan(store)


def _review(store, supplied, expected):
    cache._require(isinstance(supplied, dict), "bad_plan", "plan object")
    unsigned = {key: value for key, value in supplied.items() if key != "plan_sha256"}
    cache._require(cache._digest(cache._canonical(unsigned)) == supplied.get("plan_sha256") == expected,
                   "plan_conflict", "plan/hash differs from the reviewed migration")
    current = _plan(store)
    cache._require(current == supplied, "migration_conflict", "source inventory changed; preserve both and review a fresh plan")
    return current


def _receipt(store):
    path = store.root / RECEIPT
    receipt = cache._json(cache._read_file(path, cache.MAX_INDEX_BYTES), RECEIPT)
    cache._require(isinstance(receipt, dict) and receipt.get("format") == FORMAT and receipt.get("root") == str(store.root.resolve()),
                   "git_boundary", "missing or mismatched migration receipt")
    return receipt


def _tracked(store, allowed):
    tracked = _git(store.root, "ls-files", "-z").split("\x00")
    cache._require(all(name in allowed for name in tracked if name), "git_boundary", "unreviewed tracked file; preserve and inspect")


def apply(store, supplied, expected):
    with store._exclusive():
        reviewed = _review(store, supplied, expected)
        git = _root(store)
        if git.exists():
            if (store.root / RECEIPT).exists():
                prior = _receipt(store)
                cache._require(prior == reviewed, "migration_conflict", "repository was initialized with a different review")
                return {"status": "already_applied", "plan_sha256": expected, "root": reviewed["root"]}
            _owned_init(store, reviewed, git)
            cache._atomic_write(store.root / RECEIPT, _document(reviewed), 0o600)
            return {"status": "recovered", "plan_sha256": expected, "root": reviewed["root"], "committed": False}
        cache._require(not (store.root / RECEIPT).exists(), "migration_conflict", "unbound existing receipt")
        # A private cache may be located under a different repo; require an
        # explicit boundary instead of accidentally initializing a nested repo.
        cache._require(not any((parent / ".git").exists() for parent in store.root.parents),
                       "git_boundary", "ancestor is already a Git repository")
        stage = store.root / GIT_STAGE
        cache._reject_symlink(stage, "Git initialization staging")
        if stage.exists() or (store.root / INIT_RECEIPT).exists():
            needs_init = _owned_init(store, reviewed, stage / ".git", allow_empty=True)
            if needs_init:
                _git(stage, "init", "--initial-branch=knowledge-local", ".")
                _owned_init(store, reviewed, stage / ".git")
        else:
            # The canonical .git is exposed only after its exact metadata and
            # reviewed inventory have durable ownership evidence.
            # Compute the pristine template with the same restricted Git, and
            # save it BEFORE initializing the owned directory. A crash after
            # git init therefore cannot leave an unbound initialized repo.
            with tempfile.TemporaryDirectory(prefix="knowledge-git-template-", dir=store.root.parent) as folder:
                template = Path(folder)
                _git(template, "init", "--initial-branch=knowledge-local", ".")
                git_files = _file_manifest(template / ".git")
            stage.mkdir(mode=0o700)
            (stage / ".git").mkdir(mode=0o700)
            _write_control(store.root / INIT_RECEIPT,
                           {"format": "company-knowledge-init/v1", "plan": reviewed,
                            "git_identity": [(stage / ".git").stat().st_dev, (stage / ".git").stat().st_ino],
                            "git_files": git_files})
            _git(stage, "init", "--initial-branch=knowledge-local", ".")
            _owned_init(store, reviewed, stage / ".git")
        os.rename(stage / ".git", git)
        os.chmod(git, 0o700)
        cache._atomic_write(store.root / RECEIPT, _document(reviewed), 0o600)
        return {"status": "applied", "root": reviewed["root"], "plan_sha256": expected,
                "files_rewritten": 0, "committed": False, "remote_created": False}


def _owned_init(store, reviewed, git, allow_empty=False):
    evidence_path = store.root / INIT_RECEIPT
    cache._require(evidence_path.exists(), "recovery_conflict",
                   "no completed Git initialization evidence; preserve unrelated or incomplete repository for review")
    evidence = _read_control(evidence_path)
    cache._reject_symlink(git, "owned Git metadata")
    cache._require(evidence.get("format") == "company-knowledge-init/v1" and evidence.get("plan") == reviewed
                   and git.is_dir() and [git.stat().st_dev, git.stat().st_ino] == evidence.get("git_identity"),
                   "recovery_conflict", "Git directory or approved inventory differs from owned initialization")
    actual = _file_manifest(git)
    if allow_empty and not list(git.iterdir()):
        return True
    cache._require((git / "HEAD").is_file() and actual == evidence.get("git_files"), "recovery_conflict",
                   "Git metadata or approved inventory differs from owned initialization; preserve and review")
    return False


def snapshot(store, supplied, expected, owner, message):
    owner = cache._line(owner, "commit owner", 200)
    message = cache._line(message, "commit message", 500)
    with store._exclusive():
        reviewed = _review(store, supplied, expected)
        cache._require(_root(store).exists(), "migration_missing", "apply an independently reviewed migration first")
        _receipt(store)
        allowed = [item["path"] for item in reviewed["files"]] + [RECEIPT]
        _tracked(store, set(allowed))
        # A pre-staged change is another owner's Git transaction. Do not commit it.
        cache._require(not _git(store.root, "diff", "--cached", "--name-only"), "git_busy", "pre-staged changes require their owner's settlement")
        _git(store.root, "add", "--", *allowed)
        if not _git(store.root, "diff", "--cached", "--name-only"):
            return {"status": "unchanged", "commit": _git(store.root, "rev-parse", "HEAD"), "plan_sha256": expected}
        _git(store.root, "-c", "user.name=" + owner, "-c", "user.email=private-local@invalid",
             "commit", "--no-verify", "-m", message)
        return {"status": "committed", "commit": _git(store.root, "rev-parse", "HEAD"),
                "plan_sha256": expected, "owner": owner, "remote_created": False}


def _seed_sources(manifest, store):
    cache._require(isinstance(manifest, dict) and set(manifest) == {"format", "entries"}
                   and manifest["format"] == SEED_FORMAT, "bad_seed", "explicit seed manifest required")
    cache._require(isinstance(manifest["entries"], list) and 1 <= len(manifest["entries"]) <= 30,
                   "bad_seed", "bounded source selection required")
    entries, ids = [], set()
    for item in manifest["entries"]:
        cache._require(isinstance(item, dict) and set(item) == {"source", "record"}, "bad_seed", "source/hash and curated record required")
        source = item["source"]
        cache._require(isinstance(source, dict) and set(source) == {"path", "sha256"}
                       and isinstance(source["path"], str) and Path(source["path"]).is_absolute(), "bad_seed", "explicit original path/hash required")
        path = Path(source["path"])
        for ancestor in (path, *path.parents):
            cache._reject_symlink(ancestor, "seed source")
        cache._require(path.suffix in (".md", ".json"), "bad_seed", "only reviewed small Markdown/JSON research sources")
        data = cache._read_file(path, cache.MAX_BYTES)
        cache.safe_note(data)
        cache._require(cache._digest(data) == source["sha256"], "seed_conflict", "original source changed")
        archive = "origins/" + source["sha256"] + path.suffix
        record = dict(item["record"])
        cache._require(record.get("format") == cache.KNOWLEDGE_FORMAT, "bad_seed", "new curated imports need v2 classification")
        record["provenance"] = list(record.get("provenance", [])) + [
            {"url": str(path), "checked_on": record.get("checked_on"), "checked_portion": "Original source sha256=" + source["sha256"]},
            {"url": str(store.root.absolute() / archive), "checked_on": record.get("checked_on"), "checked_portion": "Byte-preserved original archive"},
        ]
        record = cache.semantic_of(record)
        cache._require(record["id"] not in ids, "bad_seed", "duplicate import id")
        ids.add(record["id"])
        entries.append({"source": source, "archive_path": archive, "record": record})
    return entries


def seed_plan(store, manifest):
    with store._shared():
        _root(store)
        index = store._mutation_index()
        entries = _seed_sources(manifest, store)
        result = {"format": SEED_FORMAT, "root": str(store.root.resolve()), "entries": entries,
                  "expect_index_sha256": cache._digest(cache._canonical(index)), "privacy_review_required": True}
        result["plan_sha256"] = cache._digest(cache._canonical(result))
        return result


def _seed_entries(store, supplied):
    entries = supplied["entries"]
    cache._require(isinstance(entries, list) and 1 <= len(entries) <= 30, "bad_seed", "seed entries")
    checked, ids = [], set()
    for entry in entries:
        cache._require(isinstance(entry, dict) and set(entry) == {"source", "archive_path", "record"}, "bad_seed", "seed entry fields")
        source = entry["source"]
        cache._require(isinstance(source, dict) and set(source) == {"path", "sha256"}
                       and isinstance(source["path"], str), "bad_seed", "source fields")
        for ancestor in (Path(source["path"]), *Path(source["path"]).parents):
            cache._reject_symlink(ancestor, "seed source")
        record = cache.semantic_of(entry["record"])
        data = cache._read_file(Path(source["path"]), cache.MAX_BYTES)
        cache.safe_note(data)
        archive = "origins/" + source["sha256"] + Path(source["path"]).suffix
        cache._require(Path(source["path"]).is_absolute() and Path(source["path"]).suffix in (".md", ".json")
                       and cache._digest(data) == source["sha256"] and entry["archive_path"] == archive,
                       "seed_conflict", "source/archive differs from review; preserve partial import and review originals")
        cache._require(record["format"] == cache.KNOWLEDGE_FORMAT and record["id"] not in ids,
                       "bad_seed", "unique classified import records required")
        ids.add(record["id"])
        stored = {**record, "revision": 1, "status": "current", "content_sha256": None,
                  "replaced_by": None, "conflict_with": None}
        stored["content_sha256"] = cache.content_sha256(stored)
        checked.append((record, stored, {archive: data,
                       f"records/{record['id']}.json": _document(stored),
                       f"records/{record['id']}.md": cache.render_markdown(stored).encode("utf-8")}))
    return checked


def seed_apply(store, supplied, expected):
    cache._require(isinstance(supplied, dict) and supplied.get("format") == SEED_FORMAT, "bad_seed", "seed plan required")
    cache._require(cache._digest(cache._canonical({k: v for k, v in supplied.items() if k != "plan_sha256"})) == supplied.get("plan_sha256") == expected,
                   "plan_conflict", "seed plan differs from reviewed hash")
    cache._require(supplied["root"] == str(store.root.resolve()), "seed_conflict", "seed root differs")
    with store._exclusive():
        _root(store)
        index = store._mutation_index()
        checked = _seed_entries(store, supplied)  # Always recheck originals, even on replay.
        journal_dir = store.root / SEED_JOURNALS
        cache._reject_symlink(journal_dir, "seed journals")
        journal_path = journal_dir / (expected + ".json")
        current_by_id = {row["id"]: row for row in index}
        for record, stored, outputs in checked:
            if record["id"] in current_by_id:
                current = store._read_record(record["id"])
                if current["status"] != "current" or {k: current[k] for k in cache.semantic_fields(current)} != record:
                    store._write_conflict(current, record)
            for name, data in outputs.items():
                path = store.root / name
                cache._reject_symlink(path.parent, "seed output directory")
                if path.exists() or path.is_symlink():
                    # Exact bytes are necessary but not sufficient: unindexed
                    # existing files also need this plan's pre-write journal.
                    cache._require(cache._read_file(path, cache.MAX_BYTES) == data,
                                   "seed_conflict", "partial output differs; preserved: " + name)
        if journal_path.exists():
            journal = _read_control(journal_path)
            cache._require(journal.get("format") == "company-knowledge-seed-progress/v1"
                           and journal.get("plan") == supplied, "recovery_conflict", "seed recovery plan differs")
        else:
            complete = [r["id"] for r, _, _ in checked if r["id"] in current_by_id]
            for record, _, outputs in checked:
                archive = store.root / next(iter(outputs))
                if record["id"] in current_by_id:
                    cache._require(archive.exists(), "seed_conflict", "existing seed has no original archive")
                else:
                    cache._require(not any(p.exists() or p.is_symlink() for p in store._paths(record["id"])),
                                   "seed_conflict", "unindexed import has no ownership journal; preserve and review")
            if len(complete) == len(checked):
                return {"status": "already_seeded", "ids": complete, "plan_sha256": expected}
            cache._require(cache._digest(cache._canonical(index)) == supplied["expect_index_sha256"],
                           "seed_conflict", "peer index changed; review a fresh seed plan")
            files, excluded = _inventory(store)
            journal = {"format": "company-knowledge-seed-progress/v1", "plan": supplied,
                       "base_index": index, "base_files": files, "base_excluded": excluded}
            cache._mkdir(journal_dir)
            _write_control(journal_path, journal)  # Before any imported archive/record/index write.
        base = journal["base_index"]
        cache._require(cache._digest(cache._canonical(base)) == supplied["expect_index_sha256"],
                       "recovery_conflict", "seed baseline index differs")
        baseline = {row["id"]: row for row in base}
        new = {r["id"]: (r, s, o) for r, s, o in checked if r["id"] not in baseline}
        allowed_rows = {**baseline, **{i: store._entry(s) for i, (_, s, _) in new.items()}}
        cache._require(all(row == allowed_rows.get(row["id"]) for row in index)
                       and all(row == current_by_id.get(row["id"]) for row in base),
                       "seed_conflict", "index changed outside this seed; preserve and review")
        for record, _, files in checked:
            if record["id"] in current_by_id:
                cache._require(all((store.root / name).is_file() for name in files),
                               "seed_conflict", "indexed import has missing outputs; preserve and review")
        # Validate the entire baseline and every existing partial byte before
        # repairing even one missing file. No conflicting data is overwritten.
        for item in journal["base_files"]:
            name = item["path"]
            cache._require(isinstance(name, str) and not Path(name).is_absolute() and ".." not in Path(name).parts,
                           "recovery_conflict", "unsafe baseline path")
            if name != "index.json":
                data = cache._read_file(store.root / name, cache.MAX_BYTES)
                cache._require(cache._digest(data) == item["sha256"] and len(data) == item["bytes"],
                               "seed_conflict", "baseline file changed; preserved: " + name)
        outputs = {name: data for _, _, files in checked for name, data in files.items()}
        files, excluded = _inventory(store)
        baseline_names = {item["path"] for item in journal["base_files"]}
        cache._require(all(item["path"] in baseline_names or item["path"] in outputs for item in files)
                       and sorted(name for name in excluded if name not in outputs) == journal["base_excluded"],
                       "seed_conflict", "files changed outside this seed; preserve and review")
        complete = [r["id"] for r, _, _ in checked if r["id"] in current_by_id]
        if len(complete) == len(checked):
            return {"status": "already_seeded", "ids": complete, "plan_sha256": expected}
        cache._mkdir(store.root / "origins")
        for record, stored, files in checked:
            if record["id"] in current_by_id:
                continue
            archive_name, archive_data = next(iter(files.items()))
            archive = store.root / archive_name
            if not archive.exists():
                cache._atomic_write(archive, archive_data, 0o600)
            if not any(path.exists() for path in store._paths(record["id"])):
                store._insert_locked(record, index)
            else:
                for name, data in files.items():
                    if not (store.root / name).exists():
                        cache._atomic_write(store.root / name, data, 0o600)
                index.append(store._entry(stored))
                store._write_index(index)
        return {"status": "seeded", "ids": [r["id"] for r, _, _ in checked],
                "plan_sha256": expected, "originals_rewritten": 0, "committed": False}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    seed = sub.add_parser("seed-plan")
    seed.add_argument("--manifest", type=Path, required=True)
    for command in ("apply", "snapshot", "seed-apply"):
        item = sub.add_parser(command)
        item.add_argument("--plan", type=Path, required=True)
        item.add_argument("--expect-plan-sha256", required=True)
        if command == "snapshot":
            item.add_argument("--owner", required=True)
            item.add_argument("--message", required=True)
    args = parser.parse_args(argv)
    try:
        store = cache.Store(args.root or cache._default_root(), False)
        if args.command == "plan":
            result = {"status": "planned", "plan": plan(store)}
        elif args.command == "seed-plan":
            result = {"status": "planned", "plan": seed_plan(store, cache._load_input(args.manifest))}
        else:
            supplied = cache._json(cache._read_file(args.plan, cache.MAX_INDEX_BYTES), "migration plan")
            result = (seed_apply(store, supplied, args.expect_plan_sha256) if args.command == "seed-apply" else
                      apply(store, supplied, args.expect_plan_sha256) if args.command == "apply" else
                      snapshot(store, supplied, args.expect_plan_sha256, args.owner, args.message))
        return cache._emit(result, 0)
    except cache.CacheError as exc:
        return cache._emit({"status": "error", "error": exc.code, "detail": exc.detail}, 2)
    except (OSError, subprocess.TimeoutExpired, KeyError, TypeError, ValueError) as exc:
        return cache._emit({"status": "error", "error": "unavailable", "detail": type(exc).__name__}, 2)


if __name__ == "__main__":
    sys.exit(main())
