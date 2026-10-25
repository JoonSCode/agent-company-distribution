#!/usr/bin/env python3
"""Private research records. Stdlib only: no shell, network, daemon, or delete."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

FORMAT = "company-research-record/v1"
KNOWLEDGE_FORMAT = "company-knowledge-record/v2"
INDEX_FORMAT = "company-research-index/v1"
CONFLICT_FORMAT = "company-research-conflict/v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
URL_RE = re.compile(r"^https://[^\s]+$")
ARTIFACT_RE = re.compile(r"^run-artifact:[A-Za-z0-9][A-Za-z0-9._/-]{0,160}$")
STOP = frozenset(
    "a an the of and or to for in on with without from by at as is are was be "
    "this that it its into over under".split()
)
SEMANTIC = (
    "format", "id", "stability", "topic", "problem", "query",
    "synthesis", "provenance", "scope", "version", "checked_on", "freshness",
    "uncertainty", "counterevidence", "disposition", "disposition_reason",
    "observed_use", "owner", "replaces",
)
CONTROL = ("revision", "status", "content_sha256", "replaced_by", "conflict_with")
LINE_LIMIT = 2000
TEXT_LIMIT = 8000
OPTIONAL_LINES = (
    "problem", "query", "version", "uncertainty", "counterevidence",
    "disposition_reason", "owner",
)
DISPOSITIONS = ("unset", "adopted", "adapted", "deferred", "rejected")
FRESHNESS_FIELDS = ("recheck_trigger", "review_after", "live_check_still_required", "live_check_required")
MAX_BYTES = 256_000
MAX_INDEX_BYTES = 2_000_000
KNOWLEDGE_FIELDS = ("kind", "claim", "scope_level", "applicability", "source_authority", "verification", "tags")
KINDS = ("research", "lesson", "correction", "failure", "insight", "reference")
CLAIMS = ("observation", "hypothesis", "preference", "decision")
SCOPE_LEVELS = ("project", "role", "global")
# A narrow rejection boundary, not a complete privacy classifier.
SECRET_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b|(?i:authorization\s*:\s*bearer\s+\S+)")


def safe_note(data):
    _require(not SECRET_RE.search(data.decode("utf-8", errors="replace")), "secret_detected", "credential-shaped content; keep it outside knowledge")


def semantic_fields(payload):
    return SEMANTIC + (("knowledge",) if payload.get("format") == KNOWLEDGE_FORMAT else ())


def _knowledge(value):
    _require(isinstance(value, dict) and set(value) == set(KNOWLEDGE_FIELDS), "bad_record", "knowledge metadata fields")
    _require(value["kind"] in KINDS, "bad_record", "knowledge kind")
    _require(value["claim"] in CLAIMS, "bad_record", "knowledge claim")
    _require(value["scope_level"] in SCOPE_LEVELS, "bad_record", "knowledge scope_level")
    result = {key: value[key] for key in ("kind", "claim", "scope_level")}
    for key in ("applicability", "source_authority", "verification"):
        result[key] = _line(value[key], key, LINE_LIMIT)
    tags = value["tags"]
    _require(isinstance(tags, list) and len(tags) <= 20, "bad_record", "knowledge tags")
    result["tags"] = [_line(tag, "tag", 100) for tag in tags]
    _require(len(set(result["tags"])) == len(tags), "bad_record", "duplicate tags")
    return result


class CacheError(Exception):
    def __init__(self, code, detail, status="error"):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def _require(condition, code, detail):
    if not condition:
        raise CacheError(code, detail)


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "duplicate_key", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _date(value, label):
    _require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "bad_date", label)
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise CacheError("bad_date", label) from exc
    return value


def _line(value, label, limit, allow_empty=False):
    _require(isinstance(value, str), "bad_field", f"{label} must be a string")
    _require("\n" not in value and "\x00" not in value, "bad_field", f"{label} must be one line")
    _require(allow_empty or value.strip(), "bad_field", f"{label} is empty")
    _require(len(value) <= limit, "bad_field", f"{label} is too long")
    return value


def _text(value, label, limit):
    _require(isinstance(value, str) and value.strip(), "bad_field", f"{label} is empty")
    _require("\x00" not in value and len(value) <= limit, "bad_field", f"{label} is too long")
    return value


def _optional_line(payload, key):
    if key not in payload or payload[key] is None:
        return ""
    return _line(payload[key], key, LINE_LIMIT, allow_empty=True)


def _provenance_url(url):
    """https, a run-artifact id, or an explicit local path the owner already holds."""
    _require(isinstance(url, str) and url and "\n" not in url and "\x00" not in url, "bad_record", "provenance url")
    _require(len(url) <= 500 and ".." not in url, "bad_record", "provenance url")
    if URL_RE.fullmatch(url) or ARTIFACT_RE.fullmatch(url) or url.startswith("/") or url.startswith("file://"):
        return url
    raise CacheError("bad_record", "provenance url")


def _identifier(value, label):
    _require(isinstance(value, str) and ID_RE.fullmatch(value), "bad_id", label)
    return value


def semantic_of(payload):
    """Validate a caller record and return the durable semantic fields."""
    _require(isinstance(payload, dict), "bad_record", "record must be an object")
    unknown = set(payload) - set(semantic_fields(payload)) - set(CONTROL)
    _require(not unknown, "bad_record", "unknown fields: " + ", ".join(sorted(unknown)))
    smuggled = [key for key in CONTROL if key in payload]
    _require(not smuggled, "bad_record", "control fields are store-owned: " + ", ".join(smuggled))
    _require(payload.get("format") in (FORMAT, KNOWLEDGE_FORMAT), "bad_record", "unsupported record format")
    record = {"format": payload["format"], "id": _identifier(payload.get("id"), "id")}
    if record["format"] == KNOWLEDGE_FORMAT:
        record["knowledge"] = _knowledge(payload.get("knowledge"))
        safe_note(_canonical(payload))
    _require(payload.get("stability") in ("stable_concept", "volatile_fact"), "bad_record", "stability")
    record["stability"] = payload["stability"]
    record["topic"] = _line(payload.get("topic"), "topic", LINE_LIMIT)
    record["synthesis"] = _text(payload.get("synthesis"), "synthesis", TEXT_LIMIT)
    for key in OPTIONAL_LINES:
        record[key] = _optional_line(payload, key)
    provenance = payload.get("provenance")
    _require(isinstance(provenance, list) and provenance, "bad_record", "provenance is required")
    cleaned = []
    for item in provenance:
        _require(isinstance(item, dict), "bad_record", "provenance item must be an object")
        _require(set(item) <= {"url", "checked_portion", "checked_on"}, "bad_record", "provenance fields")
        _require({"url", "checked_on"} <= set(item), "bad_record", "provenance fields")
        portion = item.get("checked_portion", "")
        cleaned.append({
            "url": _provenance_url(item["url"]),
            "checked_portion": _line("" if portion is None else portion, "checked_portion", LINE_LIMIT, allow_empty=True),
            "checked_on": _date(item["checked_on"], "checked_on"),
        })
    record["provenance"] = cleaned
    record["scope"] = _line(payload.get("scope"), "scope", LINE_LIMIT)
    record["checked_on"] = _date(payload.get("checked_on"), "checked_on")
    freshness = payload.get("freshness", {})
    _require(isinstance(freshness, dict), "bad_record", "freshness")
    _require(set(freshness) <= set(FRESHNESS_FIELDS), "bad_record", "freshness fields")
    if "live_check_required" in freshness:
        live = freshness["live_check_required"]
        _require(type(live) is bool, "bad_record", "live_check_required must be boolean")
    else:
        live = record["stability"] == "volatile_fact"
    if record["stability"] == "volatile_fact":
        _require(live is True, "bad_record", "a volatile fact cannot treat a cached date as a live check")
    if freshness.get("review_after") is not None:
        review_after = _date(freshness["review_after"], "review_after")
        _require(review_after >= record["checked_on"], "bad_record", "review_after precedes checked_on")
    elif record["stability"] == "volatile_fact":
        try:
            review_after = (dt.date.fromisoformat(record["checked_on"]) + dt.timedelta(days=7)).isoformat()
        except OverflowError as exc:
            raise CacheError("bad_date", "checked_on cannot fit the review checkpoint") from exc
    else:
        review_after = None
    record["freshness"] = {
        "recheck_trigger": _line(freshness.get("recheck_trigger", ""), "recheck_trigger", LINE_LIMIT, allow_empty=True),
        "review_after": review_after,
        "live_check_still_required": _line(
            freshness.get("live_check_still_required", ""), "live_check_still_required", LINE_LIMIT, allow_empty=True,
        ),
        "live_check_required": live,
    }
    disposition = payload.get("disposition", "unset")
    _require(disposition in DISPOSITIONS, "bad_record", "disposition")
    record["disposition"] = disposition
    observed = payload.get("observed_use")
    if observed is None or "observed_use" not in payload:
        record["observed_use"] = None
    else:
        _require(isinstance(observed, dict) and set(observed) == {"result", "observed_on", "limits"}, "bad_record", "observed_use")
        record["observed_use"] = {
            "result": _line(observed["result"], "result", LINE_LIMIT),
            "observed_on": _date(observed["observed_on"], "observed_on"),
            "limits": _line(observed["limits"], "limits", LINE_LIMIT),
        }
    replaces = payload.get("replaces")
    if replaces is not None:
        replaces = _identifier(replaces, "replaces")
        _require(replaces != record["id"], "bad_record", "a record cannot replace itself")
    record["replaces"] = replaces
    _require(len(_canonical(record)) <= MAX_BYTES // 2, "too_large", "curated record exceeds its storage boundary")
    return record


def content_sha256(record):
    # The optimistic token binds both evidence and every stored state transition.
    bound = {key: value for key, value in record.items() if key != "content_sha256"}
    return _digest(_canonical(bound))


def _json(data, label):
    try:
        return json.loads(data, object_pairs_hook=_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CacheError("bad_json", f"{label}: malformed JSON") from exc


def tokens(text):
    found = []
    for raw in TOKEN_RE.findall(text.lower()):
        if len(raw) < 2 or raw in STOP:
            continue
        found.append(raw)
    return found


def render_markdown(stored):
    provenance = "\n".join(
        f"- {item['url']} — {item['checked_portion']} ({item['checked_on']})"
        for item in stored["provenance"]
    )
    observed = stored["observed_use"]
    observed_text = "없음" if observed is None else (
        f"{observed['result']} ({observed['observed_on']}; {observed['limits']})"
    )
    lines = [
        f"# {stored['topic']}",
        "",
        f"- id: {stored['id']}",
        f"- revision: {stored['revision']}",
        f"- status: {stored['status']}",
        f"- stability: {stored['stability']}",
        f"- content_sha256: {stored['content_sha256']}",
        "",
        "## Problem",
        "",
        stored["problem"],
        "",
        "## Query",
        "",
        stored["query"],
        "",
        "## Synthesis",
        "",
        stored["synthesis"],
        "",
        "## Provenance",
        "",
        provenance,
        "",
        "## Scope and version",
        "",
        f"- scope: {stored['scope']}",
        f"- version: {stored['version'] or 'unspecified'}",
        f"- checked_on: {stored['checked_on']}",
        "",
        "## Freshness",
        "",
        f"- review_after: {stored['freshness']['review_after'] or 'none'}",
        f"- recheck_trigger: {stored['freshness']['recheck_trigger']}",
        f"- live_check_required: {str(stored['freshness']['live_check_required']).lower()}",
        f"- live_check_still_required: {stored['freshness']['live_check_still_required']}",
        "",
        "A cached date does not prove the source is still true.",
        "",
        "## Uncertainty and counterevidence",
        "",
        stored["uncertainty"],
        "",
        stored["counterevidence"],
        "",
        "## Disposition",
        "",
        f"{stored['disposition']}: {stored['disposition_reason']}",
        "",
        "## Observed use",
        "",
        observed_text,
        "",
        "## Owner and replacement",
        "",
        f"- owner: {stored['owner']}",
        f"- replaces: {stored['replaces'] or 'none'}",
        f"- replaced_by: {stored['replaced_by'] or 'none'}",
        f"- conflict_with: {stored['conflict_with'] or 'none'}",
        "",
    ]
    if stored["format"] == KNOWLEDGE_FORMAT:
        lines.extend(["## Knowledge classification", "", *[
            f"- {key}: {stored['knowledge'][key]}" for key in KNOWLEDGE_FIELDS
        ], "", "Stored evidence is not an execution instruction or automatic policy promotion.", ""])
    return "\n".join(lines)


def _default_root():
    """Use the Company record home, including an Orca runtime that shares it.

    `run_completion.default_home` already prefers SEJONG_HOME, then the canonical
    installed Company home when this package is that install and the caller is
    the standard Orca runtime or a shared skills link. A second cache rooted
    only at the terminal CODEX_HOME would split the records.
    """
    from run_completion import default_home
    return default_home() / "knowledge" / "research"


def _reject_symlink(path, label):
    if path.is_symlink():
        raise CacheError("unsafe_path", f"{label} is a symlink")


def _read_file(path, limit):
    _reject_symlink(path, str(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CacheError("unavailable", f"{path.name}: {exc.strerror}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CacheError("unsafe_path", f"{path.name} is not a regular file")
        chunks = []
        size = 0
        while True:
            block = os.read(descriptor, 65536)
            if not block:
                break
            size += len(block)
            _require(size <= limit, "too_large", path.name)
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _atomic_write(path, data, mode):
    _require(len(data) <= MAX_INDEX_BYTES, "too_large", path.name)
    _reject_symlink(path.parent, str(path.parent))
    if path.exists():
        _reject_symlink(path, path.name)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{_digest(data)[:8]}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, mode)
    try:
        view = data
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    os.close(descriptor)
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    os.chmod(path, mode)


def _mkdir(path):
    _reject_symlink(path, str(path))
    previous = os.umask(0o077)
    try:
        path.mkdir(parents=True, exist_ok=True)
    finally:
        os.umask(previous)
    _reject_symlink(path, str(path))
    _require(path.is_dir(), "unsafe_path", f"{path} is not a directory")
    os.chmod(path, 0o700)


class Store:
    def __init__(self, root, create):
        self.root = Path(root).expanduser()
        _reject_symlink(self.root, "cache root")
        if not self.root.exists():
            _require(create, "cache_absent", "research cache does not exist")
        if create:
            _mkdir(self.root)
        _require(self.root.is_dir(), "unsafe_path", "cache root is not a directory")
        self.records = self.root / "records"
        self.history = self.root / "history"
        self.conflicts = self.root / "conflicts"
        self.index_path = self.root / "index.json"
        self.lock_path = self.root / "lock"
        if create:
            os.chmod(self.root, 0o700)
            for path in (self.records, self.history, self.conflicts):
                _mkdir(path)
            with self._exclusive():
                if not self.index_path.exists():
                    _require(not any(self.records.iterdir()), "index_missing", "existing records have no index")
                    self._write_index([])
                else:
                    self._load_index()

    def _lock(self):
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        return os.open(self.lock_path, flags, 0o600)

    def _exclusive(self):
        return _Lock(self._lock(), exclusive=True)

    def _shared(self):
        return _Lock(self._lock(), exclusive=False)

    def _write_index(self, records):
        payload = {"format": INDEX_FORMAT, "records": sorted(records, key=lambda item: item["id"])}
        _atomic_write(self.index_path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), 0o600)

    def _load_index(self):
        if not self.index_path.exists():
            raise CacheError("index_missing", "index is missing; records were not scanned")
        data = _read_file(self.index_path, MAX_INDEX_BYTES)
        payload = _json(data, "index")
        _require(isinstance(payload, dict) and set(payload) == {"format", "records"}, "bad_index", "index object")
        _require(payload["format"] == INDEX_FORMAT and isinstance(payload["records"], list), "bad_index", "index")
        seen = set()
        for item in payload["records"]:
            required = {"id", "status", "stability", "topic", "problem", "query", "scope", "version",
                        "checked_on", "review_after", "recheck_trigger", "disposition", "revision",
                        "content_sha256", "excerpt", "record_path"}
            _require(isinstance(item, dict) and set(item) in (required, required | {"knowledge"}), "bad_index", "index entry fields")
            if "knowledge" in item:
                _knowledge(item["knowledge"])
            record_id = _identifier(item["id"], "index id")
            _require(record_id not in seen, "bad_index", "duplicate record id")
            seen.add(record_id)
            _require(item["status"] in ("current", "stale", "contradicted"), "bad_index", "index status")
            _require(item["stability"] in ("stable_concept", "volatile_fact"), "bad_index", "index stability")
            _require(type(item["revision"]) is int and item["revision"] > 0, "bad_index", "index revision")
            _require(isinstance(item["content_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", item["content_sha256"]), "bad_index", "index hash")
            _require(item["disposition"] in DISPOSITIONS, "bad_index", "index disposition")
            _require(item["record_path"] == f"records/{record_id}.md", "bad_index", "index path")
            _date(item["checked_on"], "index checked_on")
            if item["review_after"] is not None:
                _date(item["review_after"], "index review_after")
            for key in ("topic", "problem", "query", "scope", "version", "recheck_trigger", "excerpt"):
                _line(item[key], f"index {key}", LINE_LIMIT, allow_empty=key not in ("topic", "scope"))
        return payload["records"]

    def _mutation_index(self):
        # Reads stay index-only. Writers verify existing evidence before any write.
        index = self._load_index()
        for entry in index:
            stored = self._read_record(entry["id"])
            _require(entry == self._entry(stored), "index_record_mismatch", entry["id"])
        return index

    def _entry(self, stored):
        entry = {
            "id": stored["id"],
            "status": stored["status"],
            "stability": stored["stability"],
            "topic": stored["topic"],
            "problem": stored["problem"],
            "query": stored["query"],
            "scope": stored["scope"],
            "version": stored["version"],
            "checked_on": stored["checked_on"],
            "review_after": stored["freshness"]["review_after"],
            "recheck_trigger": stored["freshness"]["recheck_trigger"],
            "disposition": stored["disposition"],
            "revision": stored["revision"],
            "content_sha256": stored["content_sha256"],
            "excerpt": " ".join(stored["synthesis"].split())[:240],
            "record_path": f"records/{stored['id']}.md",
        }
        if stored["format"] == KNOWLEDGE_FORMAT:
            entry["knowledge"] = stored["knowledge"]
        return entry

    def _paths(self, record_id):
        return self.records / f"{record_id}.json", self.records / f"{record_id}.md"

    def _write_record(self, stored):
        json_path, markdown_path = self._paths(stored["id"])
        body = (json.dumps(stored, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        markdown = render_markdown(stored).encode("utf-8")
        _require(len(body) <= MAX_BYTES and len(markdown) <= MAX_BYTES, "too_large", "record body")
        _atomic_write(json_path, body, 0o600)
        _atomic_write(markdown_path, markdown, 0o600)

    def _read_record(self, record_id):
        _identifier(record_id, "id")
        json_path, markdown_path = self._paths(record_id)
        _require(json_path.is_file(), "missing_record", record_id)
        stored = _json(_read_file(json_path, MAX_BYTES), record_id)
        _require(isinstance(stored, dict), "bad_record", "stored record object")
        _require(set(stored) == set(semantic_fields(stored)) | set(CONTROL), "bad_record", "stored record fields")
        semantic = {key: stored[key] for key in semantic_fields(stored)}
        # Canonical stable notes store a null review date; caller input omits it.
        validation = {**semantic, "freshness": dict(semantic["freshness"])} if isinstance(semantic["freshness"], dict) else semantic
        if isinstance(validation["freshness"], dict) and validation["freshness"].get("review_after") is None:
            validation["freshness"].pop("review_after", None)
        _require(semantic_of(validation) == semantic, "bad_record", "stored semantic fields")
        _require(stored["id"] == record_id, "id_mismatch", "stored id differs")
        _require(type(stored["revision"]) is int and stored["revision"] > 0, "bad_record", "stored revision")
        _require(stored["status"] in ("current", "stale", "contradicted"), "bad_record", "stored status")
        for key in ("replaced_by", "conflict_with"):
            if stored[key] is not None:
                _identifier(stored[key], key)
        _require((stored["status"] == "current") == (stored["replaced_by"] is None), "bad_record", "stored replacement state")
        _require(content_sha256(stored) == stored["content_sha256"], "record_hash_mismatch", record_id)
        _require(_read_file(markdown_path, MAX_BYTES) == render_markdown(stored).encode("utf-8"), "record_markdown_mismatch", record_id)
        return stored

    def _archive(self, stored):
        folder = self.history / stored["id"]
        _mkdir(folder)
        revision = stored["revision"]
        _atomic_write(folder / f"{revision}.json", (json.dumps(stored, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), 0o600)
        _atomic_write(folder / f"{revision}.md", render_markdown(stored).encode("utf-8"), 0o600)

    def put(self, payload):
        semantic = semantic_of(payload)
        with self._exclusive():
            index = self._mutation_index()
            return self._insert_locked(semantic, index)

    def _insert_locked(self, semantic, index):
        """Shared insertion primitive; the caller must hold this store's lock."""
        _require(all(item["id"] != semantic["id"] for item in index), "already_exists", semantic["id"])
        _require(not any(path.exists() for path in self._paths(semantic["id"])), "unindexed_record", semantic["id"])
        stored = {**semantic, "revision": 1, "status": "current", "content_sha256": None,
                  "replaced_by": None, "conflict_with": None}
        stored["content_sha256"] = content_sha256(stored)
        self._write_record(stored)
        index.append(self._entry(stored))
        self._write_index(index)
        return stored

    def _write_conflict(self, current, rejected_semantic, code="conflict", detail=None):
        rejected = content_sha256(rejected_semantic)
        folder = self.conflicts / current["id"]
        _mkdir(folder)
        name = f"{current['content_sha256']}-{rejected}.json"
        document = {
            "format": CONFLICT_FORMAT,
            "id": current["id"],
            "retained_revision": current["revision"],
            "actual_sha256": current["content_sha256"],
            "rejected_sha256": rejected,
            "rejected_record": rejected_semantic,
        }
        _atomic_write(folder / name, (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), 0o600)
        raise CacheError(
            code,
            detail or "current record kept; rejected update stored beside it",
            status="conflict",
        )

    def update(self, record_id, payload, expect):
        _require(re.fullmatch(r"[0-9a-f]{64}", expect or ""), "bad_hash", "expect-sha256")
        semantic = semantic_of(payload)
        _require(semantic["id"] == record_id, "id_mismatch", "update id differs")
        with self._exclusive():
            index = self._mutation_index()
            _require(any(item["id"] == record_id for item in index), "missing_record", record_id)
            current = self._read_record(record_id)
            if current["content_sha256"] != expect:
                self._write_conflict(current, semantic)
            _require(current["status"] == "current", "record_superseded", "ordinary update/use cannot revive a replaced record")
            if current["format"] == KNOWLEDGE_FORMAT and semantic["format"] == FORMAT:
                self._write_conflict(current, semantic, "classification_required",
                                     "v1 update of v2 refused; current classification kept and rejected payload retained; submit v2 with explicit knowledge metadata")
            self._archive(current)
            stored = {
                **semantic,
                "revision": current["revision"] + 1,
                "status": "current",
                "content_sha256": None,
                "replaced_by": None,
                "conflict_with": None,
            }
            stored["content_sha256"] = content_sha256(stored)
            self._write_record(stored)
            index = [item for item in index if item["id"] != record_id]
            index.append(self._entry(stored))
            self._write_index(index)
            return stored

    def supersede(self, old_id, payload, expect, relation):
        _require(relation in ("stale", "contradicted"), "bad_status", relation)
        _require(re.fullmatch(r"[0-9a-f]{64}", expect or ""), "bad_hash", "expect-sha256")
        semantic = semantic_of(payload)
        _require(semantic["replaces"] == old_id, "bad_record", "replacement must name the record it replaces")
        _require(semantic["id"] != old_id, "bad_record", "replacement needs a new id")
        with self._exclusive():
            index = self._mutation_index()
            _require(any(item["id"] == old_id for item in index), "missing_record", old_id)
            current = self._read_record(old_id)
            if current["content_sha256"] != expect:
                self._write_conflict(current, semantic)
            _require(current["status"] == "current", "record_superseded", "replace the current successor instead")
            _require(all(item["id"] != semantic["id"] for item in index), "already_exists", semantic["id"])
            _require(not any(path.exists() for path in self._paths(semantic["id"])), "unindexed_record", semantic["id"])
            created = {
                **semantic,
                "revision": 1,
                "status": "current",
                "content_sha256": None,
                "replaced_by": None,
                "conflict_with": None,
            }
            created["content_sha256"] = content_sha256(created)
            self._write_record(created)
            self._archive(current)
            marked = dict(current)
            marked["revision"] = current["revision"] + 1
            marked["status"] = relation
            marked["replaced_by"] = created["id"]
            marked["content_sha256"] = content_sha256(marked)
            self._write_record(marked)
            retained = [item for item in index if item["id"] != old_id]
            retained.append(self._entry(created))
            retained.append(self._entry(marked))
            self._write_index(retained)
            return created, marked

    def search(self, query, limit, kind=None, scope_level=None):
        _require(kind is None or kind in KINDS, "bad_filter", "kind")
        _require(scope_level is None or scope_level in SCOPE_LEVELS, "bad_filter", "scope_level")
        if not self.root.exists() or not self.index_path.exists():
            if not self.root.exists():
                return {"status": "cache_absent", "matches": [], "loaded_record_bodies": 0, "scanned_index_records": 0}
            raise CacheError("index_missing", "index is missing; records were not scanned")
        with self._shared():
            index = self._load_index()
        query_tokens = tokens(query)
        matches = []
        for item in index:
            knowledge = item.get("knowledge", {})
            if kind is not None and knowledge.get("kind") != kind:
                continue
            if scope_level is not None and knowledge.get("scope_level") != scope_level:
                continue
            haystack = " ".join(str(item.get(key, "")) for key in ("topic", "problem", "query", "scope", "excerpt"))
            haystack += " " + " ".join(str(knowledge.get(key, "")) for key in KNOWLEDGE_FIELDS)
            overlap = sorted(set(query_tokens) & set(tokens(haystack)))
            if not overlap:
                continue
            rank = 0 if item["status"] == "current" else 1
            matches.append((len(overlap), rank, item["id"], overlap, item))
        matches.sort(key=lambda row: (-row[0], row[1], row[2]))
        selected = []
        for score, _rank, _record_id, overlap, item in matches[:limit]:
            selected.append({
                "id": item["id"], "score": score, "matched_tokens": overlap,
                "status": item["status"], "stability": item["stability"],
                "topic": item["topic"],
                "scope": item["scope"], "version": item["version"],
                "checked_on": item["checked_on"], "review_after": item["review_after"],
                "revision": item["revision"], "content_sha256": item["content_sha256"],
                "record_path": item["record_path"],
            })
            if knowledge := item.get("knowledge"):
                selected[-1]["knowledge"] = knowledge
        return {
            "status": "ok", "query": query, "scanned_index_records": len(index),
            "loaded_record_bodies": 0, "matches": selected,
        }

    def assess(self, record_id, scope, version, as_of):
        as_of = _date(as_of, "as_of")
        scope = _line(scope, "scope", LINE_LIMIT)
        version = _line(version, "version", LINE_LIMIT, allow_empty=True)
        with self._shared():
            stored = self._read_record(record_id)
        fresh = stored["freshness"]
        result = {
            "id": stored["id"], "status": stored["status"], "stability": stored["stability"],
            "revision": stored["revision"], "content_sha256": stored["content_sha256"],
            "replacement": stored["replaced_by"], "recheck_trigger": fresh["recheck_trigger"],
            "live_check_still_required": fresh["live_check_still_required"],
            "cached_date_bypasses_live_check": False,
            "record_retained": True,
        }
        if stored["format"] == KNOWLEDGE_FORMAT:
            result["knowledge"] = stored["knowledge"]
            result["authority"] = "evidence_only; source verification and scoped decision remain required"
        if stored["status"] != "current":
            result["decision"] = "not_reusable"
            result["reason"] = "The record stays visible with its replacement link and is not reused as current."
            return result
        scope_overlap = (scope == stored["scope"] if stored["format"] == KNOWLEDGE_FORMAT
                         else set(tokens(scope)) & set(tokens(stored["scope"])))
        if not scope_overlap:
            result["decision"] = "scope_mismatch"
            result["reason"] = "The query can name this topic while the requested scope does not match."
            return result
        outdated = bool(fresh["review_after"]) and as_of > fresh["review_after"]
        if outdated:
            result["decision"] = "partial_refresh"
            result["needs_live_check"] = fresh["live_check_required"] or stored["stability"] == "volatile_fact"
            result["reason"] = (
                "The checkpoint date passed. Refresh the outdated portion and keep the record. "
                "The timestamp does not prove the source is still true and does not delete a stable concept."
            )
            return result
        if fresh["live_check_required"] or stored["stability"] == "volatile_fact":
            result["decision"] = "needs_live_check"
            result["needs_live_check"] = True
            result["reason"] = "A cached date does not make a volatile or live-checked fact current."
            return result
        if version and stored["version"] and version != stored["version"]:
            result["decision"] = "partial_refresh"
            result["needs_live_check"] = False
            result["reason"] = "The requested version differs. Refresh that portion and keep the prior record."
            return result
        result["decision"] = "reuse"
        result["needs_live_check"] = False
        result["reason"] = "Scope matches and the stable concept is inside its review checkpoint."
        return result

    def digest(self):
        with self._shared():
            index = self._load_index()
        rows = [
            {"id": item["id"], "revision": item["revision"], "status": item["status"],
             "content_sha256": item["content_sha256"]}
            for item in sorted(index, key=lambda item: item["id"])
        ]
        return {"status": "ok", "records": rows, "loaded_record_bodies": 0}


class _Lock:
    def __init__(self, descriptor, exclusive):
        self.descriptor = descriptor
        self.exclusive = exclusive

    def __enter__(self):
        import fcntl
        fcntl.flock(self.descriptor, fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH)
        return self

    def __exit__(self, *_args):
        import fcntl
        fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        os.close(self.descriptor)


def _load_input(path):
    data = _read_file(Path(path), MAX_BYTES)
    return _json(data, "input")


def _emit(payload, code):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def _store(root, create):
    return Store(root or _default_root(), create)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    put = sub.add_parser("put")
    put.add_argument("--record", type=Path, required=True)
    update = sub.add_parser("update")
    update.add_argument("--id", required=True)
    update.add_argument("--record", type=Path, required=True)
    update.add_argument("--expect-sha256", required=True)
    replace = sub.add_parser("replace")
    replace.add_argument("--id", required=True)
    replace.add_argument("--record", type=Path, required=True)
    replace.add_argument("--expect-sha256", required=True)
    replace.add_argument("--relation", choices=("stale", "contradicted"), required=True)
    use = sub.add_parser("use")
    use.add_argument("--id", required=True)
    use.add_argument("--expect-sha256", required=True)
    use.add_argument("--result", required=True)
    use.add_argument("--observed-on", required=True)
    use.add_argument("--limits", required=True)
    get = sub.add_parser("get")
    get.add_argument("--id", required=True)
    search = sub.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--kind", choices=KINDS)
    search.add_argument("--scope-level", choices=SCOPE_LEVELS)
    assess = sub.add_parser("assess")
    assess.add_argument("--id", required=True)
    assess.add_argument("--scope", required=True)
    assess.add_argument("--version", default="")
    assess.add_argument("--as-of", required=True)
    opening = sub.add_parser("opening")
    opening.add_argument("--task", choices=("trivial", "consequential"), required=True)
    sub.add_parser("digest")
    args = parser.parse_args(argv)
    try:
        if args.command == "opening":
            if args.task == "trivial":
                payload = {
                    "action": "no_survey", "cache": "skip", "web": "skip",
                    "reason": "Small settled exact work takes the cheapest discriminating check without a cache or web survey. Reversibility alone is insufficient.",
                }
            else:
                payload = {
                    "action": "search_cache", "cache": "relevant_subset", "web": "gaps_only",
                    "reason": "Search the relevant cache subset first. Search externally only for a gap, mismatch, or outdated portion.",
                }
            return _emit({"status": "ok", **payload}, 0)
        create = args.command in ("init", "put", "update", "replace", "use")
        if args.command == "search" and args.root is not None and not Path(args.root).expanduser().exists():
            return _emit({"status": "cache_absent", "matches": [], "loaded_record_bodies": 0, "scanned_index_records": 0}, 0)
        if args.command == "search" and args.root is None and not _default_root().exists():
            return _emit({"status": "cache_absent", "matches": [], "loaded_record_bodies": 0, "scanned_index_records": 0}, 0)
        store = _store(args.root, create)
        if args.command == "init":
            payload = {"status": "ok", "root": str(store.root)}
        elif args.command == "put":
            payload = {"status": "ok", "record": store.put(_load_input(args.record))}
        elif args.command == "update":
            payload = {"status": "ok", "record": store.update(args.id, _load_input(args.record), args.expect_sha256)}
        elif args.command == "replace":
            created, marked = store.supersede(args.id, _load_input(args.record), args.expect_sha256, args.relation)
            payload = {"status": "ok", "record": created, "previous": marked}
        elif args.command == "use":
            with store._shared():
                current = store._read_record(args.id)
            semantic = {key: current[key] for key in semantic_fields(current)}
            semantic["observed_use"] = {
                "result": args.result, "observed_on": args.observed_on, "limits": args.limits,
            }
            payload = {"status": "ok", "record": store.update(args.id, semantic, args.expect_sha256)}
        elif args.command == "get":
            with store._shared():
                payload = {"status": "ok", "record": store._read_record(args.id), "loaded_record_bodies": 1}
        elif args.command == "search":
            _require(1 <= args.limit <= 20, "bad_limit", "limit must be 1 to 20")
            payload = store.search(args.query, args.limit, args.kind, args.scope_level)
        elif args.command == "assess":
            decision = store.assess(args.id, args.scope, args.version, args.as_of)
            payload = {**decision, "record_status": decision["status"], "status": "ok"}
        else:
            payload = store.digest()
        code = 4 if payload.get("status") == "conflict" else 0
        return _emit(payload, code)
    except CacheError as exc:
        return _emit({"status": exc.status, "error": exc.code, "detail": exc.detail}, 4 if exc.status == "conflict" else 2)
    except OSError as exc:
        return _emit({"status": "error", "error": "unavailable", "detail": exc.strerror}, 2)


if __name__ == "__main__":
    sys.exit(main())
