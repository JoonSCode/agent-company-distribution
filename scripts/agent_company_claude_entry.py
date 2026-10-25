#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Optional explicit Claude skill link. No credentials, provider hooks or role engine."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import shlex

from agent_company_config import ConfigError, resolve


def location(home: Path, claude_home: Path | None = None):
    target = home.absolute() / 'agent-company/claude-entry'
    configured = resolve(home=home)['values'].get('claude_home')
    chosen = claude_home or (Path(os.environ['CLAUDE_CONFIG_DIR']) if os.environ.get('CLAUDE_CONFIG_DIR') else None) or (Path(configured) if configured else None)
    if chosen is None and home.absolute() != (Path.home() / '.codex').absolute():
        raise ConfigError('alternate execution home requires explicit --claude-home or CLAUDE_CONFIG_DIR; real Claude home preserved')
    link = (chosen or Path.home() / '.claude').absolute() / 'skills/agent-company'
    registry = home.absolute() / 'agent-company/claude-entry.json'
    return target, link, registry


def check_parents(path: Path):
    for parent in path.parents:
        if parent.is_symlink():
            raise ConfigError(f'refuse symlink Claude entry parent: {parent}')


def verify_owned_tree(home: Path, digests: set[str], *, allow_missing=False):
    """The wrapper owns exactly one regular file, never arbitrary directory contents."""
    from agent_company_install_fs import anchored_parent, entry_stat, hash_at, OPEN_DIR
    import stat
    target = home.absolute() / 'agent-company/claude-entry'
    if allow_missing and not target.exists() and not target.is_symlink():
        return
    with anchored_parent(home, 'agent-company/claude-entry', create=False) as (parent, name):
        metadata = entry_stat(parent, name)
        if metadata is None or not stat.S_ISDIR(metadata.st_mode):
            raise ConfigError('Claude wrapper directory changed; preserve it for review')
        directory = os.open(name, OPEN_DIR, dir_fd=parent)
        try:
            if set(os.listdir(directory)) != {'SKILL.md'}:
                raise ConfigError('Claude wrapper has additional or missing entries; preserve user files for review')
            if hash_at(directory, 'SKILL.md', 'file') not in digests:
                raise ConfigError('Claude wrapper changed; preserve it for review')
        finally:
            os.close(directory)


def preflight_restore(paths, base: Path, entries):
    """Before any recovery/rollback mutation, accept only recorded old/new wrapper bytes."""
    if not any(entry.relative == 'agent-company/claude-entry' for entry in entries):
        return
    from agent_company_install_managed_fs import read_path_bytes
    from agent_company_install_fs import safe_relative
    registry = paths.root / 'claude-entry.json'
    documents = []
    if registry.exists() or registry.is_symlink():
        documents.append(json.loads(read_path_bytes(registry)))
    for entry in entries:
        if entry.relative == 'agent-company/claude-entry.json' and entry.kind != 'absent':
            documents.append(json.loads(read_path_bytes(base / safe_relative(entry.backup))))
    digests = set()
    for document in documents:
        if not isinstance(document, dict) or document.get('format') != 'company-claude-entry/v1' or document.get('home') != str(paths.codex_home.absolute()) or document.get('target') != str(paths.codex_home.absolute() / 'agent-company/claude-entry'):
            raise ConfigError('refuse foreign Claude wrapper recovery ownership')
        digest = document.get('entry_sha256')
        if not isinstance(digest, str) or len(digest) != 64:
            raise ConfigError('Claude wrapper recovery hash is missing')
        digests.add(digest)
    verify_owned_tree(paths.codex_home, digests, allow_missing=True)


def preflight(home: Path, claude_home: Path | None = None):
    target, link, registry = location(home, claude_home)
    check_parents(link); check_parents(registry)
    prior = None
    if registry.is_symlink():
        raise ConfigError('Claude ownership registry is a symlink')
    if registry.exists():
        prior = json.loads(registry.read_text())
        if prior.get('format') != 'company-claude-entry/v1' or prior.get('home') != str(home.absolute()) or prior.get('link') != str(link):
            raise ConfigError('Claude entry ownership differs; use its original installation home to remove it')
    if prior is None and (target.exists() or target.is_symlink()):
        raise ConfigError('unowned Claude wrapper directory; preserve existing path')
    if link.exists() or link.is_symlink():
        if not prior or not link.is_symlink() or os.readlink(link) != str(target):
            raise ConfigError(f'Claude skill collision; preserve existing path: {link}')
    elif prior:
        raise ConfigError('owned Claude entry is missing; repair explicitly before update')
    if prior:
        verify_owned_tree(home, {prior.get('entry_sha256')})
    return target, link, registry, prior


def install(home: Path, claude_home: Path | None = None):
    target, link, registry, prior = preflight(home, claude_home)
    template = home / 'skills/company-orchestration/assets/claude-entry.md'
    if not template.is_file() or template.is_symlink():
        raise ConfigError('managed Claude template is missing')
    paths = ('- Company entry: ' + str(home / 'skills/agent-company/SKILL.md') + '\n'
             '- Operating policy: ' + str(home / 'skills/company-orchestration/SKILL.md') + '\n'
             '- Configuration: run the installed snapshot scripts/agent_company_config.py explain --home ' + shlex.quote(str(home)) + '. Read ' + str(home / 'agent-company/active.json') + ' for its snapshot path.\n'
             '- Set CODEX_HOME only for this command to ' + shlex.quote(str(home)) + '; the directory is storage, not a Codex credential requirement.')
    rendered = template.read_text().replace('{{COMPANY_PATHS}}', paths)
    from agent_company_install_io import install_paths
    from agent_company_install_managed_fs import replace_managed
    with tempfile.TemporaryDirectory(prefix='company-claude-entry-') as raw:
        staged = Path(raw) / 'entry'; staged.mkdir()
        (staged / 'SKILL.md').write_text(rendered)
        replace_managed(install_paths(home), staged, 'agent-company/claude-entry')
    digest = hashlib.sha256(rendered.encode()).hexdigest()
    payload = {'format': 'company-claude-entry/v1', 'home': str(home.absolute()),
               'link': str(link), 'target': str(target), 'entry_sha256': digest}
    registry.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(dir=registry.parent, prefix='.claude-entry-', delete=False) as stream:
            temp = Path(stream.name)
            stream.write((json.dumps(payload, indent=2) + '\n').encode()); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, registry)
        if not prior:
            link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.symlink(str(target), link)  # Never replace a collision.
    except BaseException:
        if not prior and link.is_symlink() and os.readlink(link) == str(target):
            link.unlink()
        raise
    finally:
        if 'temp' in locals():
            temp.unlink(missing_ok=True)
    return {'status': 'installed', 'link': str(link), 'target': str(target), 'sha256': digest,
            'scope': 'Explicit /agent-company discovery only; no Claude runtime/auth/hook claim.'}


def remove(home: Path, claude_home: Path | None = None):
    target, link, registry, prior = preflight(home, claude_home)
    if not prior:
        return {'status': 'absent'}
    link.unlink(); registry.unlink()
    from agent_company_install_io import install_paths
    from agent_company_install_managed_fs import remove_managed
    remove_managed(install_paths(home), 'agent-company/claude-entry')
    return {'status': 'removed', 'link': str(link)}


def restore_link(home: Path, desired: bytes | None):
    """Called by the existing transaction's restore_entries; only this allowed root."""
    registry = home.absolute() / 'agent-company/claude-entry.json'
    if desired is None and not registry.exists() and not registry.is_symlink():
        return  # This transaction never owned an external Claude entry.
    target, link, registry = location(home)
    check_parents(link)
    current = json.loads(registry.read_bytes()) if registry.exists() else None
    before = json.loads(desired) if desired is not None else None
    for doc in (current, before):
        if doc is not None and (doc.get('format') != 'company-claude-entry/v1' or doc.get('home') != str(home.absolute()) or doc.get('link') != str(link) or doc.get('target') != str(target)):
            raise ConfigError('refuse foreign Claude entry restore')
    if link.exists() or link.is_symlink():
        if current is None or not link.is_symlink() or os.readlink(link) != str(target):
            raise ConfigError('Claude restore collision; unrelated path preserved')
        if before is None:
            link.unlink()
    elif before is not None:
        link.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.symlink(str(target), link)
