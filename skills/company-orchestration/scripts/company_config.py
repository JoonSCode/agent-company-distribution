#!/usr/bin/env python3
"""Canonical Markdown configuration. No provider calls, credentials or model aliases."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from dataclasses import dataclass
import fcntl

CONFIG_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'config'
SERVICES = ('codex', 'claude-code', 'antigravity', 'grok', 'cursor')
ROUTE_ALIASES = {'agy': 'antigravity', 'claude': 'claude-code'}
FIELDS = {'schema_version', 'preset', 'services', 'updater', 'api_paid', 'head_model',
          'head_effort', 'head_efforts', 'excluded_model_prefixes', 'excluded_models', 'service_order', 'max_workers', 'claude_home'}
LISTS = {'services', 'excluded_models', 'excluded_model_prefixes', 'head_efforts', 'service_order'}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Document:
    path: Path
    values: dict
    body: str
    sha256: str


def canonical_home(home: Path | None = None) -> Path:
    requested = (home or Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))).expanduser().absolute()
    if (requested / 'agent-company/active.json').is_file():
        return requested
    package = requested / 'skills/company-orchestration'
    if package.is_dir():
        resolved = package.resolve()
        installed = resolved.parent.parent
        if resolved.parent.name == 'skills' and (installed / 'agent-company/active.json').is_file():
            return installed
    # Same documented runtime-home fallback as installation_home, never arbitrary homes.
    standard = Path.home() / '.codex'
    orca_home = Path.home() / 'Library/Application Support/orca/codex-runtime-home/home'
    if requested == orca_home and not package.exists() and (standard / 'agent-company/active.json').is_file():
        return standard
    return requested


def user_path(home: Path | None = None) -> Path:
    return canonical_home(home) / 'agent-company' / 'user.md'


def read_document(path: Path) -> Document:
    if path.is_symlink() or not path.is_file():
        raise ConfigError(f'configuration must be a regular file: {path}')
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise ConfigError(f'configuration exceeds 64 KiB: {path}')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ConfigError(f'configuration is not UTF-8: {path}') from exc
    lines = text.splitlines()
    if not lines or lines[0] != '---':
        return Document(path, {}, text.strip(), hashlib.sha256(raw).hexdigest())
    if '---' not in lines[1:]:
        raise ConfigError(f'unterminated YAML front matter: {path}')
    end = lines.index('---', 1)
    values = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'([a-z_]+):[ ]*(.+)', line)
        if not match:
            raise ConfigError(f'only flat scalar keys and JSON-style YAML lists are supported: {path}')
        key, value = match.groups()
        if key in values or key not in FIELDS:
            raise ConfigError(f'duplicate or unsupported setting {key}: {path}')
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/+ -]*', value):
                raise ConfigError(f'unsupported YAML value for {key}: {path}')
            parsed = value
        values[key] = parsed
    validate(values, partial=True)
    if values.get('schema_version') != 1:
        raise ConfigError(f'unsupported schema_version: {path}')
    return Document(path, values, '\n'.join(lines[end + 1:]).strip(), hashlib.sha256(raw).hexdigest())


def validate(values: dict, *, partial=False):
    if set(values) - FIELDS:
        raise ConfigError('unsupported critical settings: ' + ', '.join(sorted(set(values) - FIELDS)))
    for key, value in values.items():
        if key in LISTS:
            if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value) or len(set(value)) != len(value):
                raise ConfigError(f'{key} must be a unique list of nonempty strings')
            if key in {'services', 'service_order'} and set(value) - set(SERVICES):
                raise ConfigError(f'unsupported service in {key}')
        elif key in {'updater', 'api_paid'}:
            if type(value) is not bool:
                raise ConfigError(f'{key} must be true or false')
        elif key == 'schema_version':
            if type(value) is not int or value != 1:
                raise ConfigError('unsupported schema_version')
        elif key == 'claude_home':
            if not isinstance(value, str) or not Path(value).is_absolute() or '..' in Path(value).parts:
                raise ConfigError('claude_home must be an absolute explicit configuration root')
        elif key == 'max_workers':
            if type(value) is not int or not 1 <= value <= 32:
                raise ConfigError('max_workers must be an integer from 1 to 32')
        elif not isinstance(value, str) or not value.strip() or '\n' in value:
            raise ConfigError(f'{key} must be nonempty text')
    if values.get('head_efforts') and values.get('head_effort') and values['head_effort'] not in values['head_efforts']:
        raise ConfigError('preferred head_effort must be in head_efforts')
    if 'preset' in values and values['preset'] not in {'single', 'multiple', 'custom'}:
        raise ConfigError('preset must be single, multiple or custom')
    if not partial and not {'schema_version', 'preset', 'services', 'updater', 'api_paid', 'excluded_models', 'service_order', 'max_workers'} <= set(values):
        raise ConfigError('resolved configuration is missing common required settings')
    if not partial and values.get('preset') == 'single' and len(values.get('services', [])) > 1:
        raise ConfigError('single preset accepts at most one service; choose multiple')


def resolve(*, home: Path | None = None, user: Path | None = None, task: Path | None = None,
            preset: str | None = None, config_root: Path = CONFIG_ROOT, include_user: bool = True) -> dict:
    """Later documents replace complete values; prose remains ordered and source-bound."""
    private = user or (Path(os.environ['AGENT_COMPANY_CONFIG']) if os.environ.get('AGENT_COMPANY_CONFIG') else user_path(home))
    task = task or (Path(os.environ['AGENT_COMPANY_TASK_CONFIG']) if os.environ.get('AGENT_COMPANY_TASK_CONFIG') else None)
    override = read_document(private) if include_user and (private.exists() or private.is_symlink()) else None
    if not include_user:
        task = None
    task_doc = read_document(task) if task else None
    choice = preset or (task_doc.values.get('preset') if task_doc else None) or (override.values.get('preset') if override else None) or 'single'
    if choice not in {'single', 'multiple', 'custom'}:
        raise ConfigError('unsupported preset')
    selected = private.parent / 'custom.md' if choice == 'custom' else config_root / 'presets' / f'{choice}.md'
    docs = [read_document(config_root / 'common.md'), read_document(selected)]
    if override:
        docs.append(override)
    if task_doc:
        docs.append(task_doc)
    values, sources = {}, {}
    for doc in docs:
        for key, value in doc.values.items():
            values[key], sources[key] = value, str(doc.path)
    # A CLI selection is current-task intent and must select the same document/value.
    if preset:
        values['preset'], sources['preset'] = preset, 'explicit --preset'
    if values.get('preset') != choice:
        raise ConfigError('selected preset and document disagree')
    validate(values)
    sources_hash = hashlib.sha256(json.dumps([d.sha256 for d in docs], sort_keys=True).encode()).hexdigest()
    return {'schema_version': 1, 'values': values, 'sources': sources, 'documents': [
        {'path': str(d.path), 'sha256': d.sha256, 'instructions': d.body} for d in docs],
        'configuration_sha256': sources_hash, 'user_document': str(private),
        'state': 'configured' if override else ('legacy_unconfigured' if (private.parent / 'active.json').exists() else 'fresh_unconfigured'),
        'limits': 'Selection is intent, never authentication or launch authority. Higher-priority safety and authority always apply.'}


def route_errors(config: dict, *, route: str, model: str, effort: str | None, billing: str,
                 head=False, explicit_pin=False) -> list[str]:
    v = config['values']
    service = ROUTE_ALIASES.get(route, route)
    errors = []
    if service not in SERVICES:
        errors.append('unsupported execution service')
    elif service not in v['services']:
        errors.append('service is not selected; configure it or supply an explicit current-task document')
    if (model in v['excluded_models'] or any(model.casefold().startswith(prefix.casefold()) for prefix in v.get('excluded_model_prefixes', []))) and not explicit_pin:
        errors.append('model is excluded by resolved configuration')
    if billing == 'paid_api' and not v['api_paid']:
        errors.append('API-paid execution requires explicit opt-in; never automatic fallback')
    if billing not in {'subscription', 'paid_api'}:
        errors.append('billing is unknown; execution is not authorized')
    if head and not explicit_pin:
        if v.get('head_model') and v['head_model'] != model:
            errors.append('head model differs from resolved user choice')
        if v.get('head_efforts') and effort not in v['head_efforts']:
            errors.append('head effort is outside resolved allowed choices')
        elif not v.get('head_efforts') and v.get('head_effort') and v['head_effort'] != effort:
            errors.append('head effort differs from resolved user choice')
    return errors


def readiness(config: dict, observations: dict | None = None) -> list[dict]:
    """Read-only supplied host evidence, never infers auth from intent or executable presence."""
    observations = observations or {}
    result = []
    for service in SERVICES:
        selected = service in config['values']['services']
        obs = observations.get(service, {})
        ok = selected and obs.get('supported') is True and obs.get('authenticated') is True and obs.get('tools') is True and obs.get('billing') in {'subscription', 'paid_api'} and bool(obs.get('evidence')) and bool(obs.get('observed_at'))
        if obs.get('billing') == 'paid_api' and not config['values']['api_paid']:
            ok = False
        result.append({'service': service, 'selected': selected, 'executable': bool(ok),
                       'status': 'usable_from_supplied_evidence' if ok else ('verification_pending' if selected else 'not_selected'),
                       'observation': obs if selected else {},
                       'limit': 'Recheck evidence freshness and current task/model/effort/host support before launch.'})
    return result


def encode(values: dict, body: str) -> str:
    validate(values, partial=True)
    return '---\n' + '\n'.join(f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in values.items()) + '\n---\n\n' + body.strip() + '\n'


def save_document(path: Path, text: str, *, expected: str | None, preserve_history: bool = True) -> str:
    """Private CAS, same-directory atomic replace; history is outside managed snapshots."""
    path = path.absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ConfigError(f'refuse symlink configuration path: {parent}')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = path.parent / '.configuration.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        old = path.read_bytes() if path.exists() else None
        digest = hashlib.sha256(old).hexdigest() if old is not None else None
        if digest != expected:
            raise ConfigError('configuration changed concurrently; re-read before saving')
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.configuration-', delete=False) as tmp:
            temp = Path(tmp.name)
            try:
                tmp.write(text.encode()); tmp.flush(); os.fsync(tmp.fileno())
                read_document(temp)
                if preserve_history and old is not None and old != text.encode():
                    history = path.parent / 'user-history'
                    if history.is_symlink():
                        raise ConfigError('refuse symlink history')
                    history.mkdir(mode=0o700, exist_ok=True)
                    backup = history / f'{path.stem}-{digest}.md'
                    if backup.is_symlink() or (backup.exists() and backup.read_bytes() != old):
                        raise ConfigError('history collision; original document and existing history preserved')
                    backup_fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600) if not backup.exists() else None
                    if backup_fd is not None:
                        with os.fdopen(backup_fd, 'wb') as stream:
                            stream.write(old); stream.flush(); os.fsync(stream.fileno())
                os.replace(temp, path)
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temp.unlink(missing_ok=True)
    finally:
        os.close(fd)
    return hashlib.sha256(text.encode()).hexdigest()


def restore_document(path: Path, original: bytes | None, *, expected: str):
    """Failure compensation: CAS restores captured bytes; never touches user history."""
    if original is not None:
        return save_document(path, original.decode('utf-8'), expected=expected, preserve_history=False)
    path = path.absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ConfigError('refuse symlink configuration restore')
    fd = os.open(path.parent / '.configuration.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ConfigError('configuration changed concurrently; preserve current document instead of restoring')
        path.unlink()
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(fd)
