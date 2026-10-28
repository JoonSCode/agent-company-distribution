#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Terminal onboarding; delegates installation to the existing transactional bootstrap."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shlex
import shutil
from pathlib import Path
import sys

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from agent_company_config import ConfigError, resolve, readiness, user_path, read_document, save_document, restore_document, encode
from company_config import SERVICES, validate
from agent_company_bootstrap import BootstrapConfig, bootstrap
from agent_company_bootstrap_sources import BootstrapError

ROOT = Path(__file__).resolve().parents[1]


def choose(prompt, default):
    answer = input(f'{prompt} [{default}]: ').strip()
    return answer or default


def main(argv=None):
    p = argparse.ArgumentParser(description='Configure Company Markdown and optionally install from reviewed clean source')
    p.add_argument('action', nargs='?', choices=['install', 'reconfigure'], default='install')
    p.add_argument('--home', type=Path, default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))))
    p.add_argument('--config', type=Path, help='Import a versioned user Markdown document')
    p.add_argument('--preset', choices=['single', 'multiple', 'custom'])
    p.add_argument('--services', help='Comma-separated intent: codex,claude-code,antigravity,grok,cursor; empty selects none')
    p.add_argument('--updater', choices=['on', 'off'])
    p.add_argument('--api-paid', choices=['on', 'off'], help='Explicit API permission, never automatic fallback')
    p.add_argument('--head-model')
    p.add_argument('--head-effort')
    p.add_argument('--head-efforts', help='Comma-separated allowed opaque head efforts; head-effort is preferred within this set')
    p.add_argument('--exclude-model', action='append')
    p.add_argument('--custom-preset', type=Path, help='Copy a modest personal preset Markdown to private custom.md')
    p.add_argument('--json', action='store_true', help='Machine-readable output, including in a terminal')
    p.add_argument('--claude-home', type=Path, help='Explicit Claude configuration root (or CLAUDE_CONFIG_DIR), for isolated homes')
    p.add_argument('--no-input', action='store_true')
    p.add_argument('--yes', action='store_true', help='Apply the printed plan without confirmation')
    p.add_argument('--dry-run', action='store_true', help='Configuration preview only: no configuration writes or installer/preflight/provider calls; use shell wrapper to block runtime downloads')
    args = p.parse_args(argv)
    try:
        return setup(args)
    except (KeyboardInterrupt, EOFError):
        print('취소했습니다. 적용 중이었다면 위 복원 결과를 확인하세요. 패키지 상태는 별도 확인이 필요합니다.', file=sys.stderr)
        return 130
    except (ConfigError, BootstrapError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def setup(args):
    home = args.home.expanduser().absolute()
    destination = user_path(home)
    existing = read_document(destination) if destination.exists() or destination.is_symlink() else None
    original_bytes = destination.read_bytes() if existing else None
    imported = read_document(args.config) if args.config else existing
    values = dict(imported.values) if imported else {}
    values.setdefault('schema_version', 1)
    body = imported.body if imported else '# My Company configuration\n\nPrivate user choices. Service selection is intent; verify host support, authentication and billing before execution.'
    interactive = sys.stdin.isatty() and not args.no_input
    preset = args.preset or values.get('preset', 'single')
    services = args.services
    updater = args.updater
    if interactive and not args.yes and not args.dry_run:
        print('서비스: Codex=codex · Claude Code 직접=claude-code · Antigravity(Claude 별도 경로)=antigravity · Grok=grok · Cursor=cursor')
        print('선택은 인증이 아닙니다. 설치되는 native 역할·hook은 현재 Codex 호스트 통합이며 다른 서비스의 전역 설정은 바꾸지 않습니다.')
        if services is None:
            services = choose('사용할 서비스, 쉼표 구분; none은 나중에 연결', ','.join(values.get('services', [])) or 'none')
        if updater is None:
            updater = choose('자동 updater on / off', 'on' if values.get('updater', False) else 'off')
    if services is not None:
        values['services'] = [] if services in ('', 'none') else [s.strip() for s in services.split(',')]
    # Derive only fresh choices. Explicit, imported and existing presets/overrides win.
    if args.preset is None and 'preset' not in values and not args.custom_preset:
        preset = 'multiple' if len(values.get('services', [])) > 1 else 'single'
    values['preset'] = preset
    if updater is not None:
        if updater not in ('on', 'off'):
            raise ConfigError('updater must be on or off')
        values['updater'] = updater == 'on'
    if args.claude_home:
        values['claude_home'] = str(args.claude_home.expanduser().absolute())
    if args.api_paid:
        values['api_paid'] = args.api_paid == 'on'
    for key in ('head_model', 'head_effort'):
        if getattr(args, key) is not None:
            values[key] = getattr(args, key)
    if args.head_efforts is not None:
        values['head_efforts'] = [item.strip() for item in args.head_efforts.split(',')]
    if args.exclude_model is not None:
        values['excluded_models'] = args.exclude_model
    custom = read_document(args.custom_preset) if args.custom_preset else None
    if custom and (preset != 'custom' or custom.values.get('preset') != 'custom'):
        raise ConfigError('custom document must declare preset: custom and select --preset custom')
    base = resolve(home=home, preset=preset) if preset != 'custom' or not custom else resolve(home=home, preset='single')
    effective = dict(base['values'])
    if custom:
        effective.update(custom.values)
    effective.update(values)
    validate(effective)
    base['values'] = effective
    install_root = home / 'agent-company'
    depth_note = ('Desktop Settings → Orchestration → Nested worker depth에서 직접 확인하세요. '
                  'root 0 → lead 1 → member 2 구조는 최소 2가 필요합니다. '
                  '현재 값은 확인하지 않았으며 자동 변경하지 않습니다.')
    first_task = (f'새 Orca 세션에서 {home / "skills/agent-company/SKILL.md"}와 '
                  f'{destination}를 읽고 저장소 개선점 3개만 제안해 줘. 파일 수정·외부 게시를 하지 마.')
    plan = {'preview_scope': 'configuration_only; source/installer/runtime preflight not run',
            'installation_state': 'existing_receipt_present' if (install_root / 'active.json').exists() else 'no_active_receipt_observed',
            'install_root': str(install_root), 'nested_worker_depth': depth_note,
            'status': 'dry_run' if args.dry_run else 'plan', 'action': args.action, 'home': str(home),
            'user_document': str(destination), 'claude_home': str((args.claude_home or Path(os.environ.get('CLAUDE_CONFIG_DIR', effective.get('claude_home', str(Path.home() / '.claude'))))).expanduser().absolute()), 'configuration': effective, 'routes': readiness(base),
            'changes': ['private user.md (versioned history; preserved on package update/rollback)'] +
                       (['private custom.md'] if custom else []) +
                       (['Company snapshot, managed skills, six Codex-native role TOMLs, Codex completion hook registry',
                         'owned Claude /agent-company entry symlink if Claude direct is selected',
                         'optional daily updater registration' if effective['updater'] else 'fresh updater disabled; existing updater choice/registration preserved unless explicitly changed'] if args.action == 'install' else []),
            'hook_trust': 'Codex native /hooks trust review remains user-owned; file installation is not trusted runtime verification.',
            'host_limit': 'Selected Claude direct installs an owned explicit /agent-company skill entry; actual Claude discovery/inference remains unverified. Native role TOMLs and Stop hook target Codex only. Other services use actual Orca support and self-contained briefs. No Codex binary/credentials or provider call is required for package installation.',
            'first_safe_task': first_task,
            'verify': 'From the reported persistent Git source (not a snapshot repo), use CODEX_HOME for this home when running doctor.py and sync-status.py --json; review hook trust separately.'}
    machine_output = args.json or not sys.stdin.isatty() or args.no_input
    if machine_output:
        print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    else:
        print('\n설치 전 변경 요약' if args.action == 'install' else '\n설정 변경 요약')
        print('설정 미리보기만 수행했습니다. 소스·설치기·런타임 preflight는 아직 실행하지 않았습니다.')
        print('대상: ' + str(home))
        print('기존 설치 영수증: ' + ('있음; 상태 검증 전' if (install_root / 'active.json').exists() else '관찰되지 않음; 미설치 확정 아님'))
        print('개인 설정: ' + str(destination))
        print('프리셋: ' + {'single': '하나의 연결', 'multiple': '여러 연결', 'custom': '개인 프리셋'}[preset])
        print('선택 서비스: ' + (', '.join(effective['services']) or '나중에 연결'))
        print('연결 확인: 아직 확인하지 않음 · 선택은 인증이 아닙니다.')
        print('자동 updater: ' + ('켜짐' if effective['updater'] else '꺼짐'))
        if args.action == 'reconfigure' and args.updater is not None:
            print('updater 등록 변경은 다음 설치에 적용됩니다.')
        print('API 과금 허용: ' + ('명시적 허용; 자동 전환 없음' if effective['api_paid'] else '꺼짐'))
        print('변경: 비공개 Markdown 설정과 이전 버전 보관')
        if args.action == 'install':
            print('설치: Company 스킬·역할, Codex용 종료 hook 파일; Claude 직접 선택 시 /agent-company 진입 연결')
        print('남은 확인: Codex hook 신뢰 검토와 각 서비스의 인증·지원 모델·과금 경로')
        print(depth_note)
        print('첫 작업: ' + first_task)

    if args.dry_run:
        return 0
    if not args.yes:
        if not interactive:
            raise ConfigError('non-TTY/--no-input requires --yes to apply; use --dry-run to review')
        if choose('위 변경을 적용할까요? yes / no', 'no') != 'yes':
            print('취소했습니다. 설정 저장과 설치기를 실행하지 않았습니다.', file=sys.stderr)
            return 130
    if args.action == 'install' and shutil.which('git') is None:
        raise ConfigError('Git is required for installation from a reviewed clean persistent checkout. Install Git separately, then retry; configuration has not been saved.')
    # Save intent before activation so all installed consumers see coherent values.
    # On failure, attempt byte-for-byte CAS restoration without overwriting concurrent edits.
    # Package recovery remains owned by the existing transaction journal.
    custom_target = destination.parent / 'custom.md'
    previous_custom = custom_target.read_bytes() if custom_target.exists() else None
    expected_custom = hashlib.sha256(previous_custom).hexdigest() if previous_custom is not None else None
    save_started = []
    saved = None
    custom_saved = None
    installer_started = False
    entry_change_started = False
    result = None
    try:
        if custom:
            save_started.append(str(custom_target))
            custom_saved = save_document(custom_target, args.custom_preset.read_text(), expected=expected_custom)
        save_started.append(str(destination))
        saved = save_document(destination, encode(values, body), expected=existing.sha256 if existing else None)
        if args.claude_home:
            previous_claude_home = os.environ.get('CLAUDE_CONFIG_DIR')
            os.environ['CLAUDE_CONFIG_DIR'] = str(args.claude_home.expanduser().absolute())
        if args.action == 'install':
            installer_started = True
            result = bootstrap(BootstrapConfig('install', home, effective['updater'], files_only=True, disable_updater=(args.updater == 'off' or (imported is not None and imported.values.get('updater') is False))), source_root=ROOT)
            if machine_output:
                print(json.dumps({'installation': result}, ensure_ascii=False))
            else:
                print('설치 파일을 적용했습니다. 실행·인증·hook 신뢰 확인은 남아 있습니다.')
        elif (home / 'agent-company/active.json').exists():
            import agent_company_claude_entry as claude_entry
            if 'claude-code' in effective['services']:
                entry_change_started = True
                claude_entry.install(home)
            elif (home / 'agent-company/claude-entry.json').exists():
                entry_change_started = True
                claude_entry.remove(home)
    except BaseException as failure:
        restored, pending = [], []
        for target, before, expected in ((destination, original_bytes, saved),
                                         (custom_target, previous_custom, custom_saved)):
            if expected is not None:
                try:
                    restore_document(target, before, expected=expected)
                    restored.append(str(target))
                except (ConfigError, OSError) as exc:
                    pending.append({'path': str(target), 'error': str(exc)})
        print(json.dumps({'status': 'apply_failed', 'cause': str(failure) or type(failure).__name__,
                          'configuration_restored': restored, 'restore_pending': pending,
                          'save_outcome_unknown': [str(target) for target, expected in ((destination, saved), (custom_target, custom_saved))
                                                   if str(target) in save_started and expected is None],
                          'package_state': 'unknown; inspect existing installer journal/recovery and host entry before retry' if installer_started or entry_change_started else 'installer_and_entry_not_started',
                          'reviewed_source': str(ROOT), 'home': str(home)}, ensure_ascii=False), file=sys.stderr)
        if pending:
            raise ConfigError('Configuration restoration is incomplete; concurrent edits were not overwritten. Inspect restore_pending and the original failure before retry.') from failure
        raise
    finally:
        if args.claude_home and 'previous_claude_home' in locals():
            if previous_claude_home is None:
                os.environ.pop('CLAUDE_CONFIG_DIR', None)
            else:
                os.environ['CLAUDE_CONFIG_DIR'] = previous_claude_home
    if machine_output:
        print(json.dumps({'install_root': str(install_root),
                      'persistent_git_source': result['sources']['agent_company'] if result else None,
                      'active_receipt': str(install_root / 'active.json') if result else None,
                      'first_safe_task': first_task, 'nested_worker_depth': depth_note,
                      'status': 'files_applied_runtime_pending' if args.action == 'install' else 'configured', 'user_document': str(destination), 'sha256': saved,
                      'provider_auth': 'not checked', 'hook_trust': 'review remains user-owned'}, ensure_ascii=False))
    else:
        print('개인 설정: ' + str(destination))
        if result:
            source = result['sources']['agent_company']
            print('상태: files_applied_runtime_pending (설치 파일 적용; 실행 검증 대기)')
            print('영속 Git 소스: ' + source)
            print('설치 위치: ' + str(install_root))
            print('설치 영수증: ' + str(install_root / 'active.json'))
            print('설치 snapshot repo는 .git 없는 사본입니다. update/recover는 위 Git 소스에서 검토 후 실행하세요.')
            print('상태 점검 위치: cd ' + shlex.quote(source))
            print('상태 점검 홈: export CODEX_HOME=' + shlex.quote(str(home)))
        print('연결은 실제 인증·도구·과금 경로와 Codex hook 신뢰를 별도로 확인하세요.')
        print(depth_note)
        print('첫 작업: ' + first_task)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
