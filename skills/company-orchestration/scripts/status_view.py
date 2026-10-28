#!/usr/bin/env python3
"""Read-only local status snapshot viewer for one Company supplementary record (stdlib only)."""
from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
from pathlib import Path
import re
import sys

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_check

CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
UNSAFE_SCHEME_RE = re.compile(r'^\s*(?:javascript|data|vbscript)\s*:', re.IGNORECASE)
AUTHORITY_NOTE = (
    '기록된 주장의 내부 일관성 검사만 수행합니다. 작성자 신원, 독립 판단 여부, '
    '실제 사용자 승인 또는 현재 호스트 프로세스 생존 여부는 인증하지 않습니다.'
)
LIVE_HOST_NOTE = '저장된 정적 레코드만 읽었으며 현재 호스트/프로세스 실시간 상태는 관측하지 않음 (unknown)'


def _clean_text(value, default='—'):
    if value is None:
        return default
    text = str(value)
    return CONTROL_CHAR_RE.sub('\ufffd', text)


def _esc(value, default='—'):
    return html.escape(_clean_text(value, default), quote=True)


def _scan_control_chars(value, path='$'):
    errors = []
    if isinstance(value, str):
        if CONTROL_CHAR_RE.search(value):
            errors.append({
                'path': path,
                'code': 'invalid_control_char',
                'message': 'Disallowed ASCII control character in record string',
            })
    elif isinstance(value, dict):
        for k, v in value.items():
            key_path = f'{path}.{_clean_text(k, "")}'
            if isinstance(k, str) and CONTROL_CHAR_RE.search(k):
                errors.append({
                    'path': key_path,
                    'code': 'invalid_control_char',
                    'message': 'Disallowed ASCII control character in object key',
                })
            errors.extend(_scan_control_chars(v, key_path))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            errors.extend(_scan_control_chars(item, f'{path}[{idx}]'))
    return errors


def _scan_unsafe_refs(record):
    errors = []
    if not isinstance(record, dict):
        return errors
    evidence = record.get('evidence')
    if not isinstance(evidence, dict):
        return errors
    for eid, item in evidence.items():
        if not isinstance(item, dict):
            continue
        for field in ('ref', 'file'):
            raw = item.get(field)
            if isinstance(raw, str) and UNSAFE_SCHEME_RE.match(raw):
                errors.append({
                    'path': f'$.evidence.{_clean_text(eid, "")}.{field}',
                    'code': 'unsafe_ref_scheme',
                    'message': 'Executable or inline-data URI schemes are not permitted in evidence references',
                })
    return errors


def _errors_for_prefix(errors, prefix):
    matched = []
    for err in errors:
        path = err.get('path', '')
        if path == prefix or path.startswith(prefix + '.') or path.startswith(prefix + '['):
            matched.append(err)
    return matched


def _build_evidence_catalog(record, errors):
    label = record.get('label') if isinstance(record, dict) else None
    raw_map = record.get('evidence') if isinstance(record, dict) and isinstance(record.get('evidence'), dict) else {}
    catalog = {}
    for eid, item in raw_map.items():
        path = f'$.evidence.{eid}'
        item_errors = _errors_for_prefix(errors, path)
        if not isinstance(item, dict):
            catalog[eid] = {
                'id': str(eid),
                'kind': None,
                'ref': None,
                'sha256': None,
                'file': None,
                'binds': None,
                'verification_status': 'invalid',
                'verification_label': '유효하지 않음 (형식 오류)',
                'valid': False,
                'proof_sufficient': False,
                'errors': item_errors,
            }
            continue
        ref = item.get('ref') if isinstance(item.get('ref'), str) else None
        sha256 = item.get('sha256') if isinstance(item.get('sha256'), str) else None
        file_val = item.get('file') if isinstance(item.get('file'), str) else None
        kind = item.get('kind') if isinstance(item.get('kind'), str) else None
        binds = item.get('binds') if isinstance(item.get('binds'), dict) else None
        has_valid_sha = isinstance(sha256, str) and len(sha256) == 64 and all(c in '0123456789abcdef' for c in sha256)
        if item_errors or not ref or not kind:
            status = 'invalid'
            status_label = '검증 실패 / 무효 (' + ', '.join(sorted({e['code'] for e in item_errors})) + ')' if item_errors else '유효하지 않음 (필수 필드 누락)'
            valid = False
            proof_ok = False
        elif file_val is not None and has_valid_sha:
            status = 'file_hash_verified'
            status_label = '로컬 파일 바이트·SHA-256 대조 완료 (작성자 인증 아님)'
            valid = True
            proof_ok = True
        elif has_valid_sha:
            status = 'hash_pin_only'
            status_label = '해시 핀만 기록됨 (로컬 파일 바이트 미대조)'
            valid = True
            proof_ok = True
        elif label == 'synthetic' and kind == 'synthetic':
            status = 'synthetic_ref'
            status_label = '합성 예시 참조 (실제 해시·파일 증명 없음)'
            valid = True
            proof_ok = True
        else:
            status = 'unverified_ref_only'
            status_label = '해시·파일 증명 누락 (참조 문자열만 있음)'
            valid = True
            proof_ok = False
        catalog[eid] = {
            'id': str(eid),
            'kind': kind,
            'ref': ref,
            'sha256': sha256,
            'file': file_val,
            'binds': binds,
            'verification_status': status,
            'verification_label': status_label,
            'valid': valid,
            'proof_sufficient': proof_ok,
            'errors': item_errors,
        }
    return catalog


def _resolve_evidence_ref(ev_id, catalog, required=True):
    if ev_id is None or (isinstance(ev_id, str) and not ev_id.strip()):
        return {
            'id': None,
            'status': 'missing' if required else 'not_applicable',
            'label': '증거 참조 누락 (null)' if required else '해당 없음',
            'valid': not required,
            'proof_sufficient': not required,
            'ref': None,
            'sha256': None,
            'file': None,
            'kind': None,
        }
    if not isinstance(ev_id, str) or ev_id not in catalog:
        return {
            'id': str(ev_id),
            'status': 'unknown_evidence',
            'label': f'미등록 증거 ID ({_clean_text(ev_id)})',
            'valid': False,
            'proof_sufficient': False,
            'ref': None,
            'sha256': None,
            'file': None,
            'kind': None,
        }
    entry = catalog[ev_id]
    return {
        'id': entry['id'],
        'status': entry['verification_status'],
        'label': entry['verification_label'],
        'valid': entry['valid'],
        'proof_sufficient': entry['proof_sufficient'],
        'ref': entry['ref'],
        'sha256': entry['sha256'],
        'file': entry['file'],
        'kind': entry['kind'],
    }


def _analyze_ownership(record, catalog, errors):
    goal = record.get('goal') if isinstance(record, dict) and isinstance(record.get('goal'), dict) else {}
    raw_events = record.get('ownership') if isinstance(record, dict) and isinstance(record.get('ownership'), list) else []
    verified_owner = None
    accepted_key = None
    chain = []
    pending_proposals = []
    for idx, item in enumerate(raw_events):
        path = f'$.ownership[{idx}]'
        ev_errors = _errors_for_prefix(errors, path)
        if not isinstance(item, dict):
            chain.append({
                'index': idx,
                'revision': None,
                'scope': None,
                'from': None,
                'to': None,
                'status': 'invalid',
                'accepted_by': None,
                'evidence': _resolve_evidence_ref(None, catalog, required=True),
                'valid': False,
                'transfers_responsibility': False,
                'note': '소유권 항목 형식 오류',
                'errors': ev_errors,
            })
            continue
        rev = item.get('revision') if isinstance(item.get('revision'), str) else None
        scope = item.get('scope') if isinstance(item.get('scope'), str) else None
        frm = item.get('from') if isinstance(item.get('from'), str) else None
        to = item.get('to') if isinstance(item.get('to'), str) else None
        status = item.get('status') if isinstance(item.get('status'), str) else None
        accepted_by = item.get('accepted_by') if isinstance(item.get('accepted_by'), str) else None
        ev_info = _resolve_evidence_ref(item.get('evidence'), catalog, required=(status == 'accepted'))
        step_valid = not ev_errors and bool(rev and scope and to) and status in ('proposed', 'accepted')
        transfers = False
        if status == 'accepted':
            if accepted_by != to:
                step_valid = False
                note = '오류: 수락자(accepted_by)가 인수 대상(to)과 다름'
            elif not ev_info['proof_sufficient']:
                step_valid = False
                note = f"오류: 수락 증거 불충분 ({ev_info['label']})"
            elif frm != verified_owner:
                step_valid = False
                note = '오류: 직전 수락된 소유자로부터 이어지지 않은 체인 (owner_chain)'
            elif step_valid:
                verified_owner = to
                accepted_key = (rev, scope)
                transfers = True
                note = '유효한 소유권 인수 (책임 이전됨)'
            else:
                note = '오류: 소유권 인수 조건 미충족'
        elif status == 'proposed':
            note = '제안됨 (미수락 — 책임이 이전되지 않으며 직전 수락 소유자에게 책임 유지)'
            pending_proposals.append({
                'index': idx,
                'from': frm,
                'to': to,
                'revision': rev,
                'scope': scope,
            })
        else:
            step_valid = False
            note = '알 수 없는 소유권 상태'
        chain.append({
            'index': idx,
            'revision': rev,
            'scope': scope,
            'from': frm,
            'to': to,
            'status': status,
            'accepted_by': accepted_by,
            'evidence': ev_info,
            'valid': step_valid,
            'transfers_responsibility': transfers,
            'note': note,
            'errors': ev_errors,
        })
    goal_rev = goal.get('revision') if isinstance(goal.get('revision'), str) else None
    goal_scope = goal.get('scope') if isinstance(goal.get('scope'), str) else None
    recorded_owner = goal.get('current_owner') if isinstance(goal.get('current_owner'), str) and goal.get('current_owner').strip() else None
    recorded_acceptance = goal.get('owner_acceptance') if isinstance(goal.get('owner_acceptance'), str) else None
    owner_errors = _errors_for_prefix(errors, '$.goal.current_owner') + _errors_for_prefix(errors, '$.goal.owner_acceptance')
    scope_accepted = (
        verified_owner is not None
        and accepted_key == (goal_rev, goal_scope)
        and bool(goal_rev and goal_scope)
    )
    owner_matches_chain = (recorded_owner == verified_owner) and not _errors_for_prefix(errors, '$.goal.current_owner')
    acceptance_matches = (recorded_acceptance == ('accepted' if scope_accepted else 'pending')) and not _errors_for_prefix(errors, '$.goal.owner_acceptance')
    if not owner_matches_chain:
        owner_badge = '오류: 미승인/불일치 소유자 주장 (unaccepted_owner)'
        owner_badge_kind = 'error'
    elif verified_owner is None:
        owner_badge = '미지정 (수락된 소유자 없음 — 추론 금지)'
        owner_badge_kind = 'pending'
    elif scope_accepted and acceptance_matches:
        owner_badge = f'수락 완료 ({verified_owner})'
        owner_badge_kind = 'success'
    else:
        owner_badge = f'현 범위 수락 대기 ({verified_owner} 연속성 유지)'
        owner_badge_kind = 'pending'
    return {
        'recorded_current_owner': recorded_owner,
        'verified_accepted_owner': verified_owner,
        'owner_matches_chain': owner_matches_chain,
        'recorded_owner_acceptance': recorded_acceptance,
        'scope_accepted': scope_accepted,
        'acceptance_matches': acceptance_matches,
        'accepted_revision_scope': {'revision': accepted_key[0], 'scope': accepted_key[1]} if accepted_key else None,
        'badge': owner_badge,
        'badge_kind': owner_badge_kind,
        'chain': chain,
        'pending_proposals': pending_proposals,
        'errors': owner_errors,
    }


def _analyze_task(task, idx, goal, catalog, projections, errors, require_routing=False, require_resources=False):
    path = f'$.tasks[{idx}]'
    task_errors = _errors_for_prefix(errors, path)
    if not isinstance(task, dict):
        return {
            'index': idx,
            'id': f'invalid-task-{idx}',
            'goal_revision': None,
            'goal_scope': None,
            'scope_matches_goal': False,
            'parent': None,
            'current_dispatch': None,
            'candidate': None,
            'candidate_note': None,
            'retry_claimed': None,
            'another_writer_claimed': None,
            'owner_and_terminal': {
                'declared_actor': None,
                'observed_executor_terminal': None,
                'reported_outcome': None,
                'receipt_projection_status': None,
                'launch_state': None,
                'message_id': None,
                'run_binding_matches': None,
            },
            'model': {'requested': None, 'observed': None, 'effort_requested': None, 'effort_observed': None},
            'routing': None,
            'stages': {
                'execution': {'state': 'unknown', 'badge': '오류: 작업 형식 무효', 'badge_kind': 'error', 'earned_success': False},
                'technical': {'present': False, 'badge': '오류: 작업 형식 무효', 'badge_kind': 'error', 'earned_success': False},
                'parent_integration': {'present': False, 'badge': '오류: 작업 형식 무효', 'badge_kind': 'error', 'earned_success': False},
            },
            'resource_preflight': None,
            'resources': [],
            'errors': task_errors,
        }

    tid = task.get('id') if isinstance(task.get('id'), str) else None
    t_rev = task.get('goal_revision') if isinstance(task.get('goal_revision'), str) else None
    t_scope = task.get('goal_scope') if isinstance(task.get('goal_scope'), str) else None
    g_rev = goal.get('revision') if isinstance(goal.get('revision'), str) else None
    g_scope = goal.get('scope') if isinstance(goal.get('scope'), str) else None
    scope_matches_goal = bool(t_rev and t_scope and t_rev == g_rev and t_scope == g_scope)
    parent = task.get('parent') if isinstance(task.get('parent'), str) else None
    current_dispatch = task.get('current_dispatch') if isinstance(task.get('current_dispatch'), str) else None
    candidate = task.get('candidate') if isinstance(task.get('candidate'), str) else None
    candidate_note = task.get('candidate_note') if isinstance(task.get('candidate_note'), str) else None
    retry_claimed = task.get('retry_claimed') if isinstance(task.get('retry_claimed'), bool) else None
    another_writer_claimed = task.get('another_writer_claimed') if isinstance(task.get('another_writer_claimed'), bool) else None

    proj = projections.get(tid) if (tid and isinstance(projections, dict) and isinstance(projections.get(tid), dict)) else None
    obs = proj.get('observation') if (proj and isinstance(proj.get('observation'), dict)) else {}

    ex = task.get('execution') if isinstance(task.get('execution'), dict) else {}
    ex_state = ex.get('state') if isinstance(ex.get('state'), str) else None
    ex_actor = ex.get('actor') if isinstance(ex.get('actor'), str) else None
    ex_result_raw = ex.get('result') if isinstance(ex.get('result'), dict) else None
    ex_errors = _errors_for_prefix(errors, f'{path}.execution') + _errors_for_prefix(errors, f'{path}.retry_claimed') + _errors_for_prefix(errors, f'{path}.another_writer_claimed')
    run_binding_matches = None
    if tid in projections:
        projection_binding = proj.get('binding') if proj else None
        observation_matches = (
            obs.get('task') == tid and obs.get('dispatch') == current_dispatch
            and isinstance(obs.get('run'), str) and bool(obs['run'].strip())
        )
        if projection_binding is not None:
            run_binding_matches = isinstance(projection_binding, dict) and bool(obs.get('run')) and projection_binding.get('run') == obs.get('run')
            observation_matches = observation_matches and isinstance(projection_binding, dict) and all(
                projection_binding.get(key) == expected
                for key, expected in (('run', obs.get('run')), ('task', tid), ('dispatch', current_dispatch)))
        if not observation_matches:
            ex_errors.append({
                'path': f'$.receipt_projections.{tid}.observation',
                'code': 'projection_binding',
                'message': '관측 Run/Task/Dispatch 누락 또는 현재 작업과 불일치: 관측 정보 미검증',
            })
            obs = {}

    if ex_state == 'live':
        live_note = '기록상 live (정적 레코드이므로 현재 호스트 프로세스 생존 여부는 unknown)'
    elif ex_state == 'unknown':
        live_note = '종료 여부 미상 (unknown — 재시도 및 다른 작성자 투입 금지)'
    elif ex_state == 'exited':
        live_note = '프로세스 종료 기록됨 (미정산 — 결과 영수증 정산 필요)'
    elif ex_state == 'settled':
        live_note = '정산 완료 기록됨 (현재 호스트 실시간 상태는 별도)'
    else:
        live_note = '유효하지 않은 실행 상태'

    if ex_result_raw is not None:
        res_task = ex_result_raw.get('task')
        res_dispatch = ex_result_raw.get('dispatch')
        res_candidate = ex_result_raw.get('candidate')
        res_outcome = ex_result_raw.get('outcome')
        res_ev = _resolve_evidence_ref(ex_result_raw.get('evidence'), catalog, required=True)
        binding_ok = (
            bool(tid and current_dispatch and candidate)
            and res_task == tid
            and res_dispatch == current_dispatch
            and res_candidate == candidate
        )
        ex_result = {
            'task': res_task,
            'dispatch': res_dispatch,
            'candidate': res_candidate,
            'outcome': res_outcome,
            'binding_matches_current': binding_ok,
            'evidence': res_ev,
        }
    else:
        ex_result = None
        binding_ok = False

    ex_earned = (
        ex_state == 'settled'
        and ex_result is not None
        and ex_result['outcome'] == 'succeeded'
        and ex_result['binding_matches_current']
        and ex_result['evidence']['proof_sufficient']
        and scope_matches_goal
        and not ex_errors
    )
    if ex_errors or (ex_result is not None and not ex_result['binding_matches_current']):
        codes = sorted({e['code'] for e in ex_errors} | ({'stale_binding'} if ex_result and not ex_result['binding_matches_current'] else set()))
        ex_badge = f"오류 / 불일치 ({', '.join(codes)})"
        ex_badge_kind = 'error'
    elif ex_result is not None and not ex_result['evidence']['proof_sufficient']:
        ex_badge = f"증거 미비 ({ex_result['evidence']['label']})"
        ex_badge_kind = 'error'
    elif not scope_matches_goal:
        ex_badge = '오류: 목표 범위·리비전 불일치 (goal_binding)'
        ex_badge_kind = 'error'
    elif ex_earned:
        ex_badge = '성공 (정산됨 · 기록 일관성 확인)'
        ex_badge_kind = 'success'
    elif ex_state == 'settled' and ex_result and ex_result['outcome'] == 'failed':
        ex_badge = '실패 (정산됨)'
        ex_badge_kind = 'error'
    elif ex_state == 'live':
        ex_badge = '진행 중 (기록상 live · 현재 생존 미상)'
        ex_badge_kind = 'pending'
    elif ex_state == 'unknown':
        ex_badge = '상태 미상 (unknown)'
        ex_badge_kind = 'pending'
    else:
        ex_badge = f'미정산 ({_clean_text(ex_state, "미상")})'
        ex_badge_kind = 'pending'

    def _review_stage(field, label_ko, require_independent=False, require_parent=False):
        raw = task.get(field)
        st_errors = _errors_for_prefix(errors, f'{path}.{field}')
        if raw is None:
            return {
                'present': False,
                'verdict': None,
                'actor': None,
                'task': None,
                'dispatch': None,
                'candidate': None,
                'binding_matches_current': False,
                'actor_valid': False,
                'evidence': _resolve_evidence_ref(None, catalog, required=False),
                'earned_success': False,
                'badge': f'{label_ko} 미실시 (null)',
                'badge_kind': 'pending',
                'errors': st_errors,
            }
        if not isinstance(raw, dict):
            return {
                'present': True,
                'verdict': None,
                'actor': None,
                'task': None,
                'dispatch': None,
                'candidate': None,
                'binding_matches_current': False,
                'actor_valid': False,
                'evidence': _resolve_evidence_ref(None, catalog, required=True),
                'earned_success': False,
                'badge': f'오류: {label_ko} 형식 무효',
                'badge_kind': 'error',
                'errors': st_errors,
            }
        verdict = raw.get('verdict') if isinstance(raw.get('verdict'), str) else None
        actor = raw.get('actor') if isinstance(raw.get('actor'), str) else None
        r_task = raw.get('task')
        r_disp = raw.get('dispatch')
        r_cand = raw.get('candidate')
        r_ev = _resolve_evidence_ref(raw.get('evidence'), catalog, required=True)
        bind_ok = (
            bool(tid and current_dispatch and candidate)
            and r_task == tid
            and r_disp == current_dispatch
            and r_cand == candidate
        )
        actor_ok = bool(actor and actor.strip())
        actor_problem = None
        if require_independent and verdict == 'passed' and actor == ex_actor:
            actor_ok = False
            actor_problem = 'self_acceptance (실행자 자체 승인 금지)'
        if require_parent and actor != parent:
            actor_ok = False
            actor_problem = 'parent_binding (상위 책임자 불일치)'
        earned = (
            verdict == 'passed'
            and bind_ok
            and actor_ok
            and r_ev['proof_sufficient']
            and scope_matches_goal
            and not st_errors
        )
        if st_errors or not bind_ok or actor_problem:
            codes = sorted(
                {e['code'] for e in st_errors}
                | ({'stale_binding'} if not bind_ok else set())
            )
            detail = ', '.join(codes) if codes else (actor_problem or 'binding_error')
            badge = f'오류 / 무효 ({detail})'
            badge_kind = 'error'
        elif not r_ev['proof_sufficient']:
            badge = f"증거 미비 ({r_ev['label']})"
            badge_kind = 'error'
        elif not scope_matches_goal:
            badge = '오류: 목표 범위·리비전 불일치 (goal_binding)'
            badge_kind = 'error'
        elif earned:
            badge = '통과 (기록됨)'
            badge_kind = 'success'
        elif verdict == 'failed':
            badge = '실패 (거부됨)'
            badge_kind = 'error'
        else:
            badge = '대기 (pending)'
            badge_kind = 'pending'
        return {
            'present': True,
            'verdict': verdict,
            'actor': actor,
            'task': r_task,
            'dispatch': r_disp,
            'candidate': r_cand,
            'binding_matches_current': bind_ok,
            'actor_valid': actor_ok,
            'actor_problem': actor_problem,
            'evidence': r_ev,
            'earned_success': earned,
            'badge': badge,
            'badge_kind': badge_kind,
            'errors': st_errors,
        }

    tech_stage = _review_stage('technical', '독립 기술 검증', require_independent=True)
    parent_stage = _review_stage('parent_integration', '상위 통합', require_parent=True)

    raw_model = task.get('model') if isinstance(task.get('model'), dict) else {}
    model_view = {
        'requested': raw_model.get('requested') if isinstance(raw_model.get('requested'), str) else None,
        'observed': raw_model.get('observed') if isinstance(raw_model.get('observed'), str) else None,
        'effort_requested': raw_model.get('effort_requested') if isinstance(raw_model.get('effort_requested'), str) else None,
        'effort_observed': raw_model.get('effort_observed') if isinstance(raw_model.get('effort_observed'), str) else None,
    }

    rt_errors = _errors_for_prefix(errors, f'{path}.routing_decision')
    if 'routing_decision' in task and isinstance(task.get('routing_decision'), dict):
        rd = task['routing_decision']
        sel = rd.get('selected') if isinstance(rd.get('selected'), dict) else {}
        bind = rd.get('binding') if isinstance(rd.get('binding'), dict) else {}
        routing_view = {
            'present': True,
            'trigger': rd.get('trigger'),
            'failure_class': rd.get('failure_class'),
            'selected_reason': rd.get('selected_reason'),
            'binding': {
                'task': bind.get('task'),
                'scope': bind.get('scope'),
                'revision': bind.get('revision'),
                'attempt': bind.get('attempt'),
                'planned': bind.get('planned'),
            },
            'selected': {
                'route': sel.get('route'),
                'family': sel.get('family'),
                'model': sel.get('model'),
                'effort': sel.get('effort'),
                'supported': sel.get('supported'),
                'evidence': _resolve_evidence_ref(sel.get('evidence'), catalog, required=True),
                'reason_evidence': _resolve_evidence_ref(sel.get('reason_evidence'), catalog, required=True),
            },
            'receipt_evidence': _resolve_evidence_ref(rd.get('receipt_evidence'), catalog, required=True),
            'valid': not rt_errors,
            'errors': rt_errors,
        }
    else:
        routing_view = {
            'present': False,
            'required': require_routing,
            'valid': not rt_errors,
            'errors': rt_errors,
        }

    pre_raw = task.get('resource_preflight') if isinstance(task.get('resource_preflight'), dict) else None
    preflight_view = None
    if pre_raw is not None:
        preflight_view = {
            'host': pre_raw.get('host'),
            'cpu': pre_raw.get('cpu'),
            'ram': pre_raw.get('ram'),
            'disk': pre_raw.get('disk'),
            'evidence': _resolve_evidence_ref(pre_raw.get('evidence'), catalog, required=True),
        }

    resources_view = []
    for r_idx, res in enumerate(task.get('resources') if isinstance(task.get('resources'), list) else []):
        if not isinstance(res, dict):
            continue
        close_raw = res.get('closeout') if isinstance(res.get('closeout'), dict) else None
        resources_view.append({
            'index': r_idx,
            'host': res.get('host'),
            'key': res.get('key'),
            'kind': res.get('kind'),
            'owner': res.get('owner'),
            'allocation': res.get('allocation'),
            'reason': res.get('reason'),
            'retention': res.get('retention'),
            'closeout': {
                'disposition': close_raw.get('disposition'),
                'next_use': close_raw.get('next_use'),
                'evidence': _resolve_evidence_ref(close_raw.get('evidence'), catalog, required=True),
            } if close_raw is not None else None,
        })

    return {
        'index': idx,
        'id': tid,
        'goal_revision': t_rev,
        'goal_scope': t_scope,
        'scope_matches_goal': scope_matches_goal,
        'parent': parent,
        'current_dispatch': current_dispatch,
        'candidate': candidate,
        'candidate_note': candidate_note,
        'retry_claimed': retry_claimed,
        'another_writer_claimed': another_writer_claimed,
        'owner_and_terminal': {
            'declared_actor': ex_actor,
            'observed_executor_terminal': obs.get('executor_terminal') if isinstance(obs.get('executor_terminal'), str) else None,
            'reported_outcome': obs.get('reported_outcome') if isinstance(obs.get('reported_outcome'), str) else None,
            'receipt_projection_status': proj.get('status') if isinstance(proj, dict) else None,
            'launch_state': obs.get('launch_state') if isinstance(obs.get('launch_state'), str) else None,
            'message_id': obs.get('message') if isinstance(obs.get('message'), str) else None,
            'run_binding_matches': run_binding_matches,
        },
        'model': model_view,
        'routing': routing_view,
        'stages': {
            'execution': {
                'state': ex_state,
                'live_state_note': live_note,
                'actor': ex_actor,
                'result': ex_result,
                'earned_success': ex_earned,
                'badge': ex_badge,
                'badge_kind': ex_badge_kind,
                'errors': ex_errors,
            },
            'technical': tech_stage,
            'parent_integration': parent_stage,
        },
        'resource_preflight': preflight_view,
        'resources': resources_view,
        'errors': task_errors,
    }


def _analyze_overall_acceptance(goal, ownership_view, tasks_view, catalog, errors):
    g_status = goal.get('status') if isinstance(goal.get('status'), str) else None
    known_failure = goal.get('known_failure') if isinstance(goal.get('known_failure'), bool) else None
    g_rev = goal.get('revision') if isinstance(goal.get('revision'), str) else None
    g_scope = goal.get('scope') if isinstance(goal.get('scope'), str) else None
    raw_assess = goal.get('assessment')
    assess_errors = _errors_for_prefix(errors, '$.goal.assessment') + _errors_for_prefix(errors, '$.goal.status') + _errors_for_prefix(errors, '$.goal.known_failure')

    if raw_assess is None:
        assess_view = None
        assess_qualifies = False
    elif not isinstance(raw_assess, dict):
        assess_view = {
            'present': True,
            'revision': None,
            'scope': None,
            'verdict': None,
            'basis': None,
            'actor': None,
            'scope_matches_goal': False,
            'independent_of_owner': False,
            'evidence': _resolve_evidence_ref(None, catalog, required=True),
            'qualifies_for_overall_success': False,
        }
        assess_qualifies = False
    else:
        a_rev = raw_assess.get('revision') if isinstance(raw_assess.get('revision'), str) else None
        a_scope = raw_assess.get('scope') if isinstance(raw_assess.get('scope'), str) else None
        verdict = raw_assess.get('verdict') if isinstance(raw_assess.get('verdict'), str) else None
        basis = raw_assess.get('basis') if isinstance(raw_assess.get('basis'), str) else None
        actor = raw_assess.get('actor') if isinstance(raw_assess.get('actor'), str) else None
        ev_info = _resolve_evidence_ref(raw_assess.get('evidence'), catalog, required=True)
        scope_ok = bool(a_rev and a_scope and a_rev == g_rev and a_scope == g_scope)
        indep_ok = True
        if basis == 'independent' and actor == goal.get('current_owner'):
            indep_ok = False
        assess_qualifies = (
            verdict == 'succeeded'
            and basis in ('human', 'independent')
            and scope_ok
            and indep_ok
            and bool(actor and actor.strip())
            and ev_info['proof_sufficient']
            and not _errors_for_prefix(errors, '$.goal.assessment')
        )
        assess_view = {
            'present': True,
            'revision': a_rev,
            'scope': a_scope,
            'verdict': verdict,
            'basis': basis,
            'actor': actor,
            'scope_matches_goal': scope_ok,
            'independent_of_owner': indep_ok,
            'evidence': ev_info,
            'qualifies_for_overall_success': assess_qualifies,
        }

    all_tasks_settled_and_accepted = all(
        t['stages']['execution']['earned_success']
        and t['stages']['technical']['earned_success']
        and t['stages']['parent_integration']['earned_success']
        for t in tasks_view
    )
    earned_success = (
        g_status == 'succeeded'
        and known_failure is False
        and ownership_view['owner_matches_chain']
        and ownership_view['scope_accepted']
        and ownership_view['acceptance_matches']
        and assess_qualifies
        and all_tasks_settled_and_accepted
        and not errors
    )

    if assess_errors or (g_status == 'succeeded' and not earned_success):
        codes = sorted({e['code'] for e in assess_errors})
        if not codes:
            if assess_view and not assess_view['evidence']['proof_sufficient']:
                codes = ['missing_proof']
            elif not all_tasks_settled_and_accepted:
                codes = ['unaccepted_task_stage']
            else:
                codes = ['overall_acceptance']
        badge = f"오류 / 전체 승인 불가 ({', '.join(codes)})"
        badge_kind = 'error'
    elif earned_success:
        basis_label = '인간 승인' if assess_view['basis'] == 'human' else '독립 최종 승인'
        badge = f'승인됨 ({basis_label} 기록됨 · 정적 스냅샷)'
        badge_kind = 'success'
    elif known_failure is True or g_status == 'failed' or (assess_view and assess_view.get('verdict') == 'failed'):
        if assess_view and assess_view.get('basis') == 'team_checks':
            badge = '실패 / 미승인 (팀 점검만 기록됨 — 전체 승인 불가)'
        else:
            badge = '실패 (전체 목표 미달 / 알려진 실패)'
        badge_kind = 'error'
    elif assess_view and assess_view.get('basis') == 'team_checks':
        badge = '대기 (팀 점검만 기록됨 — 인간/독립 전체 승인 필요)'
        badge_kind = 'pending'
    elif assess_view and assess_view.get('verdict') == 'pending':
        badge = '대기 (전체 목표 평가 pending)'
        badge_kind = 'pending'
    else:
        badge = f'대기 / 미승인 (goal.status={_clean_text(g_status, "미상")}, 평가 미완료)'
        badge_kind = 'pending'

    return {
        'goal_status': g_status,
        'known_failure': known_failure,
        'assessment': assess_view,
        'all_tasks_accepted': all_tasks_settled_and_accepted,
        'earned_success': earned_success,
        'badge': badge,
        'badge_kind': badge_kind,
        'errors': assess_errors,
        'separation_note': '개별 작업의 실행·기술검증·상위통합 통과(team_checks)는 전체 목표 승인을 자동으로 성립시키지 않습니다.',
    }


def _collect_needed_decisions(record, goal_view, ownership_view, overall_view, tasks_view, usage_view, catalog, errors):
    decisions = []
    for err in errors:
        decisions.append({
            'kind': 'check_error',
            'severity': 'error',
            'path': err.get('path', '$'),
            'code': err.get('code', 'error'),
            'title': f"일관성 검사 오류 ({err.get('code', 'error')})",
            'detail': err.get('message', ''),
        })

    for eid, ev in catalog.items():
        if not ev['proof_sufficient'] and not ev['errors']:
            decisions.append({
                'kind': 'missing_proof',
                'severity': 'error',
                'path': f'$.evidence.{eid}',
                'code': 'missing_proof',
                'title': f'증거 해시·파일 증명 누락 ({eid})',
                'detail': ev['verification_label'],
            })

    if not ownership_view['owner_matches_chain']:
        decisions.append({
            'kind': 'unaccepted_owner',
            'severity': 'error',
            'path': '$.goal.current_owner',
            'code': 'unaccepted_owner',
            'title': '미승인 소유자 주장 또는 소유권 체인 불일치',
            'detail': (
                f"기록된 current_owner={_clean_text(ownership_view['recorded_current_owner'], 'null')}, "
                f"수락 체인 검증 소유자={_clean_text(ownership_view['verified_accepted_owner'], 'null')}"
            ),
        })
    elif ownership_view['verified_accepted_owner'] is None:
        decisions.append({
            'kind': 'owner_missing',
            'severity': 'pending',
            'path': '$.goal.current_owner',
            'code': 'owner_missing',
            'title': '수락된 목표 책임 소유자 없음',
            'detail': '현재 범위·리비전에 대해 명시적으로 수락(accepted)한 소유자가 없습니다 (자동 추론 금지).',
        })
    elif not ownership_view['scope_accepted'] or ownership_view['recorded_owner_acceptance'] == 'pending':
        decisions.append({
            'kind': 'owner_scope_pending',
            'severity': 'pending',
            'path': '$.goal.owner_acceptance',
            'code': 'owner_scope_pending',
            'title': '현 리비전·범위 소유권 수락 대기',
            'detail': (
                f"연속성 책임자는 {_clean_text(ownership_view['verified_accepted_owner'])}이나, "
                f"현재 범위({_clean_text(goal_view.get('scope'))}@{_clean_text(goal_view.get('revision'))})의 명시적 수락이 대기 중입니다."
            ),
        })

    for prop in ownership_view['pending_proposals']:
        decisions.append({
            'kind': 'proposed_transfer',
            'severity': 'pending',
            'path': f"$.ownership[{prop['index']}]",
            'code': 'proposed_transfer',
            'title': f"소유권 인수 제안 미수락 ({_clean_text(prop['from'], 'null')} → {_clean_text(prop['to'])})",
            'detail': 'status=proposed 상태이므로 아직 책임이 이전되지 않았습니다.',
        })

    if goal_view.get('known_failure') is True:
        decisions.append({
            'kind': 'known_failure',
            'severity': 'error',
            'path': '$.goal.known_failure',
            'code': 'known_failure',
            'title': '알려진 전체 목표 실패(known_failure=true) 기록됨',
            'detail': '개별 작업 점검이 통과하더라도 알려진 전체 실패가 해소되기 전까지 전체 성공으로 판정할 수 없습니다.',
        })

    assess = overall_view['assessment']
    if assess is None:
        decisions.append({
            'kind': 'missing_overall_assessment',
            'severity': 'pending',
            'path': '$.goal.assessment',
            'code': 'missing_overall_assessment',
            'title': '전체 목표 최종 평가(goal.assessment) 미기록',
            'detail': '인간 또는 독립 평가자의 최종 전체 목표 승인이 아직 기록되지 않았습니다.',
        })
    elif assess.get('verdict') != 'succeeded' or assess.get('basis') == 'team_checks':
        decisions.append({
            'kind': 'overall_not_accepted',
            'severity': 'error' if assess.get('verdict') == 'failed' else 'pending',
            'path': '$.goal.assessment',
            'code': 'overall_not_accepted',
            'title': f"전체 목표 미승인 (verdict={_clean_text(assess.get('verdict'))}, basis={_clean_text(assess.get('basis'))})",
            'detail': '전체 목표 성공에는 human 또는 independent 기반의 succeeded 판정이 필요합니다.',
        })

    for t in tasks_view:
        t_path = f"$.tasks[{t['index']}]"
        tid = _clean_text(t['id'], f"task-{t['index']}")
        if not t['scope_matches_goal']:
            decisions.append({
                'kind': 'task_scope_mismatch',
                'severity': 'error',
                'path': t_path,
                'code': 'goal_binding',
                'title': f'작업 {tid} 범위·리비전 불일치',
                'detail': f"작업({t['goal_scope']}@{t['goal_revision']})이 현재 목표({goal_view.get('scope')}@{goal_view.get('revision')})와 다릅니다.",
            })
        ex = t['stages']['execution']
        if not ex['earned_success']:
            decisions.append({
                'kind': 'task_execution_unresolved',
                'severity': 'error' if ex['badge_kind'] == 'error' else 'pending',
                'path': f'{t_path}.execution',
                'code': 'execution_unresolved',
                'title': f'작업 {tid} 실행 미정산 또는 실패',
                'detail': f"{ex['badge']} — {ex['live_state_note']}",
            })
        tech = t['stages']['technical']
        if not tech['earned_success']:
            decisions.append({
                'kind': 'task_technical_unresolved',
                'severity': 'error' if tech['badge_kind'] == 'error' else 'pending',
                'path': f'{t_path}.technical',
                'code': 'technical_unresolved',
                'title': f'작업 {tid} 독립 기술 검증 미통과/누락',
                'detail': tech['badge'],
            })
        par = t['stages']['parent_integration']
        if not par['earned_success']:
            decisions.append({
                'kind': 'task_parent_unresolved',
                'severity': 'error' if par['badge_kind'] == 'error' else 'pending',
                'path': f'{t_path}.parent_integration',
                'code': 'parent_integration_unresolved',
                'title': f'작업 {tid} 상위 통합 미통과/누락',
                'detail': par['badge'],
            })
        for r in t['resources']:
            if r['closeout'] is None and ex['state'] in ('exited', 'settled'):
                decisions.append({
                    'kind': 'resource_unclosed',
                    'severity': 'error',
                    'path': f"{t_path}.resources[{r['index']}].closeout",
                    'code': 'resource_closeout',
                    'title': f"작업 {tid} 종료 리소스 미정산 ({_clean_text(r['key'])})",
                    'detail': '종료/정산된 작업의 리소스에 closeout 영수증이 없습니다.',
                })

    if usage_view['total_raw_tokens'] is None:
        decisions.append({
            'kind': 'usage_unknown',
            'severity': 'pending',
            'path': '$.usage',
            'code': 'usage_unknown',
            'title': f"원시 토큰 전체 합계 미상 (coverage={_clean_text(usage_view['coverage'])})",
            'detail': '모든 기대 단위의 입·출력 원시 토큰이 완전하게 관측되지 않아 total_raw_tokens는 null로 유지됩니다 (0으로 대체하지 않음).',
        })

    return decisions


def _collect_unknowns(captured_at, tasks_view, usage_view, catalog):
    unknowns = [
        {
            'category': 'live_host_state',
            'path': '$.live_host_state',
            'description': LIVE_HOST_NOTE,
        }
    ]
    if captured_at is None:
        unknowns.append({
            'category': 'captured_at',
            'path': '$.captured_at',
            'description': '스냅샷 캡처 시각이 입력에 제공되지 않음 (생성 시각과 별도로 미제공 표시)',
        })
    if usage_view['total_raw_tokens'] is None:
        unknowns.append({
            'category': 'usage_total',
            'path': '$.usage.total_raw_tokens',
            'description': f"전체 원시 토큰 합계 미상 (coverage={_clean_text(usage_view['coverage'])}, total_raw_tokens=null — 0으로 환산 금지)",
        })
    for t in tasks_view:
        tid = _clean_text(t['id'], f"task-{t['index']}")
        t_path = f"$.tasks[{t['index']}]"
        ex_state = t['stages']['execution']['state']
        if ex_state in ('live', 'unknown'):
            unknowns.append({
                'category': 'execution_process_state',
                'path': f'{t_path}.execution.state',
                'description': f"작업 {tid} 실행 상태가 '{ex_state}'로 기록됨 — 실제 프로세스 생존/종료 미상",
            })
        missing_model = [k for k, v in t['model'].items() if v is None]
        if missing_model:
            unknowns.append({
                'category': 'model_readback',
                'path': f'{t_path}.model',
                'description': f"작업 {tid} 미관측 모델/강도 필드: {', '.join(missing_model)} (null 유지)",
            })
    for eid, ev in catalog.items():
        if ev['verification_status'] in ('hash_pin_only', 'synthetic_ref', 'unverified_ref_only'):
            unknowns.append({
                'category': 'evidence_local_bytes',
                'path': f'$.evidence.{eid}',
                'description': f"증거 '{eid}': {ev['verification_label']}",
            })
    return unknowns


def build_view(
    record,
    check_result=None,
    record_path=None,
    record_sha256=None,
    *,
    base=None,
    captured_at=None,
    generated_at=None,
    require_routing=False,
    require_resources=False,
):
    """Build a deterministic status view dict from one supplementary record and its check_record result."""
    resolved_base = Path(base) if base is not None else (Path(record_path).parent if record_path is not None else Path.cwd())
    actual_check = record_check.check_record(record, resolved_base, require_routing=require_routing)
    if require_resources and (not isinstance(record, dict) or record.get('resource_accounting') != 'required'):
        actual_check['errors'].append({
            'path': '$.resource_accounting',
            'code': 'resource_accounting',
            'message': 'Resource accounting is required for this invocation',
        })
        actual_check['ok'] = False
        actual_check['usage']['total_raw_tokens'] = None

    merged_errors = list(actual_check.get('errors', []))
    seen_err_keys = {(e.get('path'), e.get('code'), e.get('message')) for e in merged_errors}
    if isinstance(check_result, dict):
        for err in check_result.get('errors', []):
            if isinstance(err, dict):
                key = (err.get('path'), err.get('code'), err.get('message'))
                if key not in seen_err_keys:
                    merged_errors.append(err)
                    seen_err_keys.add(key)
        if check_result.get('ok') is True and not actual_check['ok']:
            mismatch = {
                'path': '$.check_result',
                'code': 'check_result_mismatch',
                'message': 'Supplied check_result claimed ok=True, but record_check detected inconsistencies',
            }
            merged_errors.append(mismatch)

    for extra_err in _scan_control_chars(record) + _scan_unsafe_refs(record):
        key = (extra_err['path'], extra_err['code'], extra_err['message'])
        if key not in seen_err_keys:
            merged_errors.append(extra_err)
            seen_err_keys.add(key)

    consistency_ok = len(merged_errors) == 0 and bool(actual_check.get('ok'))
    usage_info = actual_check.get('usage', {}) if isinstance(actual_check.get('usage'), dict) else {}
    total_raw_tokens = usage_info.get('total_raw_tokens') if consistency_ok else None

    if captured_at is None and isinstance(record, dict) and isinstance(record.get('captured_at'), str) and record['captured_at'].strip():
        captured_at = _clean_text(record['captured_at'].strip())
    elif isinstance(captured_at, str) and captured_at.strip():
        captured_at = _clean_text(captured_at.strip())
    else:
        captured_at = None

    if generated_at is None:
        generated_at = datetime.now().astimezone().isoformat(timespec='seconds')
    else:
        generated_at = _clean_text(generated_at)

    label = record.get('label') if isinstance(record, dict) and record.get('label') in ('synthetic', 'real') else 'unknown'
    catalog = _build_evidence_catalog(record, merged_errors)
    goal_raw = record.get('goal') if isinstance(record, dict) and isinstance(record.get('goal'), dict) else {}
    plan_ev = _resolve_evidence_ref(goal_raw.get('plan'), catalog, required=True)
    ownership_view = _analyze_ownership(record, catalog, merged_errors)

    projections = record.get('receipt_projections') if isinstance(record, dict) and isinstance(record.get('receipt_projections'), dict) else {}
    raw_tasks = record.get('tasks') if isinstance(record, dict) and isinstance(record.get('tasks'), list) else []
    req_routing = bool(require_routing or (isinstance(record, dict) and record.get('routing_accounting') == 'required'))
    req_resources = bool(require_resources or (isinstance(record, dict) and record.get('resource_accounting') == 'required'))
    tasks_view = [
        _analyze_task(t, idx, goal_raw, catalog, projections, merged_errors, req_routing, req_resources)
        for idx, t in enumerate(raw_tasks)
    ]

    overall_view = _analyze_overall_acceptance(goal_raw, ownership_view, tasks_view, catalog, merged_errors)
    if not plan_ev['proof_sufficient']:
        overall_view['earned_success'] = False
        if overall_view['badge_kind'] == 'success':
            overall_view['badge'] = f"오류 / 계획 증거 미비 ({plan_ev['label']})"
            overall_view['badge_kind'] = 'error'

    raw_usage = record.get('usage') if isinstance(record, dict) and isinstance(record.get('usage'), dict) else {}
    coverage = usage_info.get('coverage') if isinstance(usage_info.get('coverage'), str) else raw_usage.get('coverage')
    subtotals = usage_info.get('observed_subtotals') if isinstance(usage_info.get('observed_subtotals'), dict) else {}
    if total_raw_tokens is None:
        total_display = '미상 (null — 0으로 간주하지 않음)'
    else:
        total_display = f'{total_raw_tokens:,} (관측된 완전 합계 · 토크나이저별 단위 상이)'

    usage_view = {
        'coverage': coverage if isinstance(coverage, str) else 'unknown',
        'expected_count': len(raw_usage.get('expected')) if isinstance(raw_usage.get('expected'), list) else 0,
        'entry_count': len(raw_usage.get('entries')) if isinstance(raw_usage.get('entries'), list) else 0,
        'observed_subtotals': subtotals,
        'total_raw_tokens': total_raw_tokens,
        'total_display': total_display,
        'tokenizer_note': usage_info.get(
            'tokenizer_note',
            'Provider/tokenizer groups retain distinct counting conventions; subtotal fields contain observed counts only.',
        ),
        'usage_note': record.get('usage_note') if isinstance(record, dict) and isinstance(record.get('usage_note'), str) else None,
    }

    goal_view = {
        'id': goal_raw.get('id') if isinstance(goal_raw.get('id'), str) else None,
        'revision': goal_raw.get('revision') if isinstance(goal_raw.get('revision'), str) else None,
        'scope': goal_raw.get('scope') if isinstance(goal_raw.get('scope'), str) else None,
        'status': goal_raw.get('status') if isinstance(goal_raw.get('status'), str) else None,
        'known_failure': goal_raw.get('known_failure') if isinstance(goal_raw.get('known_failure'), bool) else None,
        'plan_evidence': plan_ev,
        'current_owner': ownership_view['recorded_current_owner'],
        'verified_accepted_owner': ownership_view['verified_accepted_owner'],
        'owner_acceptance': ownership_view['recorded_owner_acceptance'],
        'scope_accepted': ownership_view['scope_accepted'],
        'owner_matches_chain': ownership_view['owner_matches_chain'],
        'owner_badge': ownership_view['badge'],
        'owner_badge_kind': ownership_view['badge_kind'],
    }

    needed_decisions = _collect_needed_decisions(
        record, goal_view, ownership_view, overall_view, tasks_view, usage_view, catalog, merged_errors
    )
    unknowns = _collect_unknowns(captured_at, tasks_view, usage_view, catalog)

    has_invalid_proof = any(not ev['proof_sufficient'] for ev in catalog.values())
    has_stage_error = (
        not consistency_ok
        or has_invalid_proof
        or not ownership_view['owner_matches_chain']
        or overall_view['badge_kind'] == 'error'
        or any(
            t['stages']['execution']['badge_kind'] == 'error'
            or t['stages']['technical']['badge_kind'] == 'error'
            or t['stages']['parent_integration']['badge_kind'] == 'error'
            or not t['scope_matches_goal']
            for t in tasks_view
        )
    )
    earned_overall_success = bool(overall_view['earned_success'] and not has_stage_error and consistency_ok)
    if not earned_overall_success:
        overall_view['earned_success'] = False

    if not consistency_ok or has_invalid_proof or not ownership_view['owner_matches_chain']:
        overall_badge = '오류 / 무효·일관성 위반 있음 (성공 배지 부여 불가)'
        overall_status_kind = 'error'
    elif goal_view['known_failure'] is True or goal_view['status'] == 'failed' or overall_view['badge_kind'] == 'error':
        overall_badge = '실패 / 차단 요인 있음 (전체 목표 미승인)'
        overall_status_kind = 'error'
    elif earned_overall_success:
        overall_badge = '기록상 전체 목표 승인 완료 (정적 스냅샷 · 실시간 호스트 별도)'
        overall_status_kind = 'success'
    else:
        overall_badge = '진행 중 / 전체 목표 승인 대기 (미해결 항목 있음)'
        overall_status_kind = 'pending'

    next_unresolved = needed_decisions[0] if needed_decisions else None
    counts = {
        'tasks_total': len(tasks_view),
        'execution_succeeded': sum(1 for t in tasks_view if t['stages']['execution']['earned_success']),
        'technical_passed': sum(1 for t in tasks_view if t['stages']['technical']['earned_success']),
        'parent_integration_passed': sum(1 for t in tasks_view if t['stages']['parent_integration']['earned_success']),
        'needed_decisions': len(needed_decisions),
        'unknowns': len(unknowns),
        'check_errors': len(merged_errors),
    }

    return {
        'format': 'company-status-view/v1',
        'snapshot': {
            'label': label,
            'label_badge': (
                'SYNTHETIC (합성 예시 — 실제 실행·승인 증거 아님)'
                if label == 'synthetic'
                else ('REAL (기록된 주장 스냅샷 — 실시간 호스트 상태 미상)' if label == 'real' else 'UNKNOWN LABEL')
            ),
            'record_path': str(record_path) if record_path is not None else None,
            'record_sha256': record_sha256,
            'captured_at': captured_at,
            'generated_at': generated_at,
            'live_host_state': 'unknown',
            'live_host_note': LIVE_HOST_NOTE,
            'resource_accounting': record.get('resource_accounting') if isinstance(record, dict) else None,
            'routing_accounting': record.get('routing_accounting') if isinstance(record, dict) else None,
            'consistency_check': {
                'ok': consistency_ok,
                'error_count': len(merged_errors),
                'errors': merged_errors,
                'authority_note': AUTHORITY_NOTE,
            },
        },
        'summary': {
            'overall_badge': overall_badge,
            'status_kind': overall_status_kind,
            'earned_overall_success': earned_overall_success,
            'next_unresolved': next_unresolved,
            'counts': counts,
        },
        'goal': goal_view,
        'ownership': ownership_view,
        'overall_goal_acceptance': overall_view,
        'needed_decisions': needed_decisions,
        'tasks': tasks_view,
        'usage': usage_view,
        'unknowns': unknowns,
        'evidence_catalog': list(catalog.values()),
    }


def _badge_html(text, kind='neutral'):
    cls = {
        'success': 'badge badge-success',
        'pending': 'badge badge-pending',
        'error': 'badge badge-error',
        'synthetic': 'badge badge-synthetic',
        'neutral': 'badge badge-neutral',
    }.get(kind, 'badge badge-neutral')
    return f'<span class="{cls}">{_esc(text)}</span>'


def render_html(view):
    """Render one static HTML5 snapshot from a build_view() dictionary."""
    snap = view['snapshot']
    summary = view['summary']
    goal = view['goal']
    ownership = view['ownership']
    overall = view['overall_goal_acceptance']
    tasks = view['tasks']
    usage = view['usage']
    decisions = view['needed_decisions']
    unknowns = view['unknowns']
    evidence_list = view['evidence_catalog']
    check = snap['consistency_check']
    counts = summary['counts']

    label_kind = 'synthetic' if snap['label'] == 'synthetic' else ('neutral' if snap['label'] == 'real' else 'error')
    check_badge = (
        _badge_html('일관성 검사 통과 (내부 모순 0건 · 권위 인증 아님)', 'success')
        if check['ok']
        else _badge_html(f"일관성 검사 실패 (오류 {check['error_count']}건)", 'error')
    )

    next_item = summary['next_unresolved']
    if next_item is not None:
        next_kind = 'error' if next_item.get('severity') == 'error' else 'pending'
        next_html = (
            f'<div class="callout callout-{next_kind}" id="next-unresolved">'
            f'<div class="callout-header"><strong>다음 미해결·의사결정 항목</strong> '
            f'{_badge_html(next_item["code"], next_kind)} '
            f'<code>{_esc(next_item["path"])}</code></div>'
            f'<div class="callout-title">{_esc(next_item["title"])}</div>'
            f'<div class="callout-detail">{_esc(next_item["detail"])}</div>'
            f'</div>'
        )
    else:
        next_html = (
            '<div class="callout callout-success" id="next-unresolved">'
            '<div class="callout-header"><strong>다음 미해결·의사결정 항목</strong> '
            f'{_badge_html("없음 (기록상 정산 완료)", "success")}</div>'
            '<div class="callout-detail">기록된 작업·독립검증·상위통합 및 전체 목표 승인이 일관되게 정산되었습니다. '
            '단, 실시간 호스트 상태는 정적 레코드에서 관측되지 않습니다.</div>'
            '</div>'
        )

    captured_display = _esc(snap['captured_at']) if snap['captured_at'] is not None else '미제공 (null — 임의 생성 안 함)'
    proposals_html = ''
    if ownership['pending_proposals']:
        prop_items = ''.join(
            f'<li><code>{_esc(p["from"], "null")} → {_esc(p["to"])}</code> '
            f'({_esc(p["scope"])}@{_esc(p["revision"])}) — '
            f'{_badge_html("제안됨 (proposed · 미수락 · 책임 이전 안 됨)", "pending")}</li>'
            for p in ownership['pending_proposals']
        )
        proposals_html = f'<div class="sub-box"><strong>미수락 소유권 제안:</strong><ul>{prop_items}</ul></div>'

    decisions_rows = []
    for idx, d in enumerate(decisions, start=1):
        sev_kind = 'error' if d.get('severity') == 'error' else 'pending'
        decisions_rows.append(
            f'<tr>'
            f'<td>{idx}</td>'
            f'<td>{_badge_html(d["code"], sev_kind)}</td>'
            f'<td><code>{_esc(d["path"])}</code></td>'
            f'<td><strong>{_esc(d["title"])}</strong><br><span class="muted">{_esc(d["detail"])}</span></td>'
            f'</tr>'
        )
    decisions_table = (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>#</th><th>구분 코드</th><th>JSON 경로</th><th>내용 및 필요한 조치</th>'
        '</tr></thead><tbody>' + ''.join(decisions_rows) + '</tbody></table></div>'
        if decisions_rows
        else '<p class="muted">기록상 차단 요인 또는 미결 의사결정 항목이 없습니다.</p>'
    )

    ownership_rows = []
    for ev in ownership['chain']:
        st_kind = 'success' if (ev['status'] == 'accepted' and ev['valid']) else ('pending' if ev['status'] == 'proposed' else 'error')
        ev_ref = ev['evidence']
        ownership_rows.append(
            f'<tr>'
            f'<td>{ev["index"]}</td>'
            f'<td><code>{_esc(ev["scope"])}@{_esc(ev["revision"])}</code></td>'
            f'<td><code>{_esc(ev["from"], "null (최초)")}</code> → <strong><code>{_esc(ev["to"])}</code></strong></td>'
            f'<td>{_badge_html(ev["status"], st_kind)}</td>'
            f'<td><code>{_esc(ev["accepted_by"], "null")}</code></td>'
            f'<td><code>{_esc(ev_ref["id"], "null")}</code> ({_esc(ev_ref["label"])})</td>'
            f'<td>{_esc(ev["note"])}</td>'
            f'</tr>'
        )
    ownership_table = (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>#</th><th>범위@리비전</th><th>이전 (From → To)</th><th>상태</th><th>수락자</th><th>증거</th><th>판정 메모</th>'
        '</tr></thead><tbody>' + ''.join(ownership_rows) + '</tbody></table></div>'
        if ownership_rows
        else '<p class="muted">기록된 소유권 이벤트가 없습니다 (소유자 자동 추론 없음).</p>'
    )

    assess = overall['assessment']
    if assess is None:
        assess_html = '<p><strong>전체 목표 평가(<code>$.goal.assessment</code>):</strong> 미기록 (<code>null</code>)</p>'
    else:
        assess_ev = assess['evidence']
        assess_html = (
            '<dl class="kv-grid">'
            f'<dt>판정 (verdict)</dt><dd><code>{_esc(assess.get("verdict"))}</code></dd>'
            f'<dt>근거 기준 (basis)</dt><dd><code>{_esc(assess.get("basis"))}</code></dd>'
            f'<dt>평가 주체 (actor)</dt><dd><code>{_esc(assess.get("actor"))}</code></dd>'
            f'<dt>평가 범위@리비전</dt><dd><code>{_esc(assess.get("scope"))}@{_esc(assess.get("revision"))}</code> '
            f'({"목표와 일치" if assess.get("scope_matches_goal") else "오류: 목표 범위·리비전과 불일치"})</dd>'
            f'<dt>증거 (evidence)</dt><dd><code>{_esc(assess_ev.get("id"))}</code> — {_esc(assess_ev.get("label"))}</dd>'
            '</dl>'
        )

    task_rows = []
    task_details = []
    for t in tasks:
        ex = t['stages']['execution']
        tech = t['stages']['technical']
        par = t['stages']['parent_integration']
        ot = t['owner_and_terminal']
        m = t['model']
        rt = t['routing']
        scope_tag = (
            f'<code>{_esc(t["goal_scope"])}@{_esc(t["goal_revision"])}</code>'
            if t['scope_matches_goal']
            else f'<code>{_esc(t["goal_scope"])}@{_esc(t["goal_revision"])}</code> {_badge_html("범위 불일치 (goal_binding)", "error")}'
        )
        ex_res = ex['result']
        ex_bind_text = (
            f'dispatch=<code>{_esc(ex_res["dispatch"])}</code><br>'
            f'candidate=<code>{_esc(ex_res["candidate"])}</code><br>'
            f'outcome=<code>{_esc(ex_res["outcome"])}</code>'
            if ex_res is not None
            else '결과 영수증 없음 (<code>null</code>)'
        )
        if ot['reported_outcome'] is not None:
            ex_bind_text += f'<br><span class="muted">내장 영수증 발신 보고: <code>{_esc(ot["reported_outcome"])}</code> (독립 검증 아님)</span>'

        tech_text = (
            f'actor=<code>{_esc(tech["actor"])}</code><br>'
            f'dispatch=<code>{_esc(tech["dispatch"])}</code><br>'
            f'candidate=<code>{_esc(tech["candidate"])}</code>'
            if tech['present']
            else '미실시 (<code>null</code>)'
        )
        par_text = (
            f'actor=<code>{_esc(par["actor"])}</code> (parent=<code>{_esc(t["parent"])}</code>)<br>'
            f'dispatch=<code>{_esc(par["dispatch"])}</code><br>'
            f'candidate=<code>{_esc(par["candidate"])}</code>'
            if par['present']
            else '미실시 (<code>null</code>)'
        )
        terminal_text = (
            f'선언 주체: <code>{_esc(ot["declared_actor"])}</code><br>'
            f'관측 터미널: <code>{_esc(ot["observed_executor_terminal"], "미관측 (null)")}</code><br>'
            f'관측 Run 연결: {_esc({True: "기록 내 일치", False: "불일치", None: "미검증 (기준 없음)"}[ot["run_binding_matches"]])}'
        )
        model_text = (
            f'요청: <code>{_esc(m["requested"], "미상(null)")}</code> / 강도 <code>{_esc(m["effort_requested"], "미상(null)")}</code><br>'
            f'관측: <code>{_esc(m["observed"], "미상(null)")}</code> / 강도 <code>{_esc(m["effort_observed"], "미상(null)")}</code>'
        )
        task_rows.append(
            f'<tr>'
            f'<td><strong><code>{_esc(t["id"])}</code></strong><br>{scope_tag}<br>'
            f'<span class="muted">상위(parent): <code>{_esc(t["parent"])}</code></span></td>'
            f'<td>권위 시도(current_dispatch):<br><code>{_esc(t["current_dispatch"])}</code><br>'
            f'권위 후보(candidate):<br><code>{_esc(t["candidate"])}</code></td>'
            f'<td>{terminal_text}<hr class="thin">{model_text}</td>'
            f'<td>{_badge_html(ex["badge"], ex["badge_kind"])}<br><span class="small">{_esc(ex["live_state_note"])}</span><hr class="thin">{ex_bind_text}</td>'
            f'<td>{_badge_html(tech["badge"], tech["badge_kind"])}<hr class="thin">{tech_text}</td>'
            f'<td>{_badge_html(par["badge"], par["badge_kind"])}<hr class="thin">{par_text}</td>'
            f'<td>{_badge_html(overall["badge"], overall["badge_kind"])}<br><span class="small muted">전체 목표 기준 (작업 통과와 별도)</span></td>'
            f'</tr>'
        )

        rt_html = '<p class="muted">라우팅 결정 내장 안 됨</p>'
        if rt and rt.get('present'):
            sel = rt['selected']
            bind = rt['binding']
            rt_html = (
                '<dl class="kv-grid">'
                f'<dt>선택 경로 / 모델</dt><dd><code>{_esc(sel.get("route"))}</code> / <code>{_esc(sel.get("family"))}</code> / '
                f'<code>{_esc(sel.get("model"))}</code> (effort=<code>{_esc(sel.get("effort"), "null")}</code>)</dd>'
                f'<dt>선택 사유 / 트리거</dt><dd><code>{_esc(rt.get("selected_reason"))}</code> / trigger=<code>{_esc(rt.get("trigger"))}</code> '
                f'(failure_class=<code>{_esc(rt.get("failure_class"), "null")}</code>)</dd>'
                f'<dt>결정 바인딩</dt><dd>task=<code>{_esc(bind.get("task"))}</code>, attempt=<code>{_esc(bind.get("attempt"))}</code>, '
                f'scope=<code>{_esc(bind.get("scope"))}@{_esc(bind.get("revision"))}</code>, planned=<code>{_esc(bind.get("planned"))}</code></dd>'
                f'<dt>사유 증거 / 영수증 증거</dt><dd>reason=<code>{_esc(sel["reason_evidence"]["id"])}</code>, '
                f'receipt=<code>{_esc(rt["receipt_evidence"]["id"])}</code></dd>'
                '</dl>'
            )

        res_items = []
        for r in t['resources']:
            close = r['closeout']
            close_str = (
                f'disposition=<code>{_esc(close["disposition"])}</code>, '
                f'evidence=<code>{_esc(close["evidence"]["id"])}</code>, '
                f'next_use=<code>{_esc(close["next_use"], "null")}</code>'
                if close is not None
                else '<span class="text-error">미정산 (closeout=null)</span>'
            )
            res_items.append(
                f'<li><code>{_esc(r["host"])}:{_esc(r["key"])}</code> ({_esc(r["kind"])}, '
                f'allocation=<code>{_esc(r["allocation"])}</code>, retention=<code>{_esc(r["retention"])}</code>) — {close_str}</li>'
            )
        res_html = f'<ul>{"".join(res_items)}</ul>' if res_items else '<p class="muted">할당된 리소스 항목 없음</p>'

        err_items = ''.join(
            f'<li><code>{_esc(e["path"])}</code> [{_esc(e["code"])}]: {_esc(e["message"])}</li>'
            for e in t['errors']
        )
        err_block = f'<div class="sub-box"><strong>작업 관련 오류:</strong><ul>{err_items}</ul></div>' if err_items else ''

        task_details.append(
            f'<details class="detail-card" {"open" if t["errors"] else ""}>'
            f'<summary>작업 상세 · 라우팅 · 리소스 정산 보기: <code>{_esc(t["id"])}</code> '
            f'({_esc(ex["badge"])} | 기술검증: {_esc(tech["badge"])} | 상위통합: {_esc(par["badge"])})</summary>'
            f'<div class="detail-body">'
            f'<p><strong>재시도 주장(retry_claimed):</strong> <code>{_esc(t["retry_claimed"])}</code> | '
            f'<strong>다른 작성자 주장(another_writer_claimed):</strong> <code>{_esc(t["another_writer_claimed"])}</code></p>'
            f'{f"<p><strong>후보 메모:</strong> {_esc(t["candidate_note"])}</p>" if t["candidate_note"] else ""}'
            f'<h4>라우팅 결정 (<code>routing_decision</code>)</h4>{rt_html}'
            f'<h4>리소스 정산 (<code>resources</code>)</h4>{res_html}'
            f'{err_block}'
            f'</div></details>'
        )

    tasks_table_html = (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>작업 / 범위</th>'
        '<th>현재 시도(Dispatch) 및 후보(Candidate)</th>'
        '<th>담당 주체 · 관측 터미널 · 모델</th>'
        '<th>1단계: 실행 정산<br>(Execution)</th>'
        '<th>2단계: 독립 기술 검증<br>(Technical Acceptance)</th>'
        '<th>3단계: 상위 통합<br>(Parent Integration)</th>'
        '<th>전체 목표 승인<br>(Overall Goal Acceptance)</th>'
        '</tr></thead><tbody>' + ''.join(task_rows) + '</tbody></table></div>'
        if task_rows
        else '<p class="muted">기록된 현재 범위 작업(tasks)이 없습니다.</p>'
    )

    subtotal_rows = []
    for group, sub in sorted(usage['observed_subtotals'].items()):
        in_val = f'{sub["input"]:,}' if isinstance(sub.get('input'), int) else '미상 (null)'
        out_val = f'{sub["output"]:,}' if isinstance(sub.get('output'), int) else '미상 (null)'
        subtotal_rows.append(
            f'<tr><td><code>{_esc(group)}</code></td>'
            f'<td>{sub.get("observed_entries", 0)}</td>'
            f'<td><code>{_esc(in_val)}</code></td>'
            f'<td><code>{_esc(out_val)}</code></td></tr>'
        )
    subtotals_html = (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>공급자 / 토크나이저 그룹</th><th>관측 엔트리 수</th><th>관측 입력(inclusive input)</th><th>관측 출력(inclusive output)</th>'
        '</tr></thead><tbody>' + ''.join(subtotal_rows) + '</tbody></table></div>'
        if subtotal_rows
        else '<p class="muted">관측된 공급자·토크나이저 부분합이 없습니다.</p>'
    )

    unknown_items = ''.join(
        f'<li><code>{_esc(u["path"])}</code> ({_esc(u["category"])}): {_esc(u["description"])}</li>'
        for u in unknowns
    )

    ev_rows = []
    for ev in evidence_list:
        ev_kind = 'success' if ev['verification_status'] == 'file_hash_verified' else ('error' if not ev['proof_sufficient'] else 'neutral')
        binds_str = json.dumps(ev['binds'], ensure_ascii=False, sort_keys=True) if ev['binds'] else None
        file_line = f'<br><span class="muted">file: <code>{_esc(ev["file"])}</code></span>' if ev['file'] else ''
        binds_line = f'<br><span class="muted">binds: <code>{_esc(binds_str)}</code></span>' if binds_str else ''
        ev_rows.append(
            f'<tr>'
            f'<td><code>{_esc(ev["id"])}</code></td>'
            f'<td><code>{_esc(ev["kind"])}</code></td>'
            f'<td>{_badge_html(ev["verification_label"], ev_kind)}</td>'
            f'<td><code>{_esc(ev["sha256"], "null")}</code></td>'
            f'<td><code>{_esc(ev["ref"], "null")}</code>{file_line}{binds_line}</td></tr>'
        )
    ev_table = (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>증거 ID</th><th>종류(kind)</th><th>해시·바이트 검증 상태</th><th>SHA-256</th><th>참조(ref) / 로컬 파일(file)</th>'
        '</tr></thead><tbody>' + ''.join(ev_rows) + '</tbody></table></div>'
        if ev_rows
        else '<p class="muted">기록된 증거 항목이 없습니다.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
  <title>Agent Company 상태 스냅샷 — {_esc(goal.get('id'), 'unknown')}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f8fafc;
      --surface: #ffffff;
      --surface-alt: #f1f5f9;
      --text: #0f172a;
      --muted: #475569;
      --border: #cbd5e1;
      --accent: #1d4ed8;
      --success-bg: #dcfce7;
      --success-text: #166534;
      --success-border: #86efac;
      --pending-bg: #fef9c3;
      --pending-text: #854d0e;
      --pending-border: #fde047;
      --error-bg: #fee2e2;
      --error-text: #991b1b;
      --error-border: #fca5a5;
      --synth-bg: #f3e8ff;
      --synth-text: #6b21a8;
      --synth-border: #d8b4fe;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0b1120;
        --surface: #111827;
        --surface-alt: #1e293b;
        --text: #f1f5f9;
        --muted: #94a3b8;
        --border: #334155;
        --accent: #60a5fa;
        --success-bg: #052e16;
        --success-text: #86efac;
        --success-border: #166534;
        --pending-bg: #422006;
        --pending-text: #fde047;
        --pending-border: #854d0e;
        --error-bg: #450a0a;
        --error-text: #fca5a5;
        --error-border: #991b1b;
        --synth-bg: #3b0764;
        --synth-text: #e9d5ff;
        --synth-border: #7e22ce;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 1.25rem;
      font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard", "Malgun Gothic", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    main {{ max-width: 1360px; margin: 0 auto; }}
    h1, h2, h3, h4 {{ margin-top: 0; }}
    h1 {{ font-size: 1.45rem; margin-bottom: 0.5rem; }}
    h2 {{ font-size: 1.15rem; margin-bottom: 0.75rem; border-bottom: 1px solid var(--border); padding-bottom: 0.35rem; }}
    code {{
      font-family: "SFMono-Regular", ui-monospace, Menlo, Consolas, monospace;
      font-size: 0.86em;
      background: var(--surface-alt);
      padding: 0.1rem 0.3rem;
      border-radius: 4px;
      word-break: break-all;
    }}
    .banner, .section-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem 1.15rem;
      margin-bottom: 1rem;
    }}
    .badge-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; align-items: center; }}
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 600;
      border: 1px solid var(--border);
      background: var(--surface-alt);
      color: var(--text);
    }}
    .badge-success {{ background: var(--success-bg); color: var(--success-text); border-color: var(--success-border); }}
    .badge-pending {{ background: var(--pending-bg); color: var(--pending-text); border-color: var(--pending-border); }}
    .badge-error {{ background: var(--error-bg); color: var(--error-text); border-color: var(--error-border); }}
    .badge-synthetic {{ background: var(--synth-bg); color: var(--synth-text); border-color: var(--synth-border); }}
    .callout {{
      border-left: 4px solid var(--border);
      padding: 0.75rem 1rem;
      border-radius: 6px;
      background: var(--surface-alt);
      margin-bottom: 0.9rem;
    }}
    .callout-error {{ border-left-color: var(--error-text); background: var(--error-bg); color: var(--error-text); }}
    .callout-pending {{ border-left-color: var(--pending-text); background: var(--pending-bg); color: var(--pending-text); }}
    .callout-success {{ border-left-color: var(--success-text); background: var(--success-bg); color: var(--success-text); }}
    .callout-title {{ font-weight: 700; margin-top: 0.25rem; }}
    .grid-4 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(275px, 1fr));
      gap: 0.85rem;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 1rem;
    }}
    .card {{
      background: var(--surface-alt);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.85rem;
    }}
    .kv-grid {{
      display: grid;
      grid-template-columns: minmax(120px, auto) 1fr;
      gap: 0.3rem 0.65rem;
      margin: 0;
      font-size: 0.9rem;
    }}
    .kv-grid dt {{ color: var(--muted); font-weight: 600; }}
    .kv-grid dd {{ margin: 0; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 0.55rem 0.65rem;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: var(--surface-alt); font-weight: 700; }}
    .muted {{ color: var(--muted); }}
    .small {{ font-size: 0.8rem; }}
    .text-error {{ color: var(--error-text); font-weight: 700; }}
    hr.thin {{ border: none; border-top: 1px solid var(--border); margin: 0.4rem 0; }}
    .detail-card {{
      border: 1px solid var(--border);
      border-radius: 6px;
      margin-top: 0.6rem;
      background: var(--surface-alt);
    }}
    .detail-card summary {{
      cursor: pointer;
      padding: 0.6rem 0.85rem;
      font-weight: 600;
    }}
    .detail-card summary:focus-visible, a:focus-visible {{
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }}
    .detail-body {{ padding: 0.75rem 0.95rem; border-top: 1px solid var(--border); background: var(--surface); }}
    .sub-box {{ margin-top: 0.6rem; padding: 0.55rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; }}
    @media (max-width: 768px) {{
      body {{ padding: 0.65rem; }}
      .grid-2, .grid-4 {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <header class="banner" id="top-summary">
    <h1>Agent Company 보조 레코드 정적 상태 스냅샷</h1>
    <div class="badge-row">
      {_badge_html(snap['label_badge'], label_kind)}
      {_badge_html(summary['overall_badge'], summary['status_kind'])}
      {check_badge}
      {_badge_html("실시간 호스트 상태: 미관측 (live_host_state=unknown)", "neutral")}
    </div>
    <p class="small muted">{_esc(check['authority_note'])}</p>
    {next_html}
    <div class="grid-4">
      <div class="card">
        <h3>1. 목표 및 범위 (Goal)</h3>
        <dl class="kv-grid">
          <dt>목표 ID</dt><dd><code>{_esc(goal.get('id'))}</code></dd>
          <dt>범위 @ 리비전</dt><dd><code>{_esc(goal.get('scope'))}@{_esc(goal.get('revision'))}</code></dd>
          <dt>기록된 목표 상태</dt><dd><code>{_esc(goal.get('status'))}</code></dd>
          <dt>알려진 실패 여부</dt><dd><code>{_esc(goal.get('known_failure'))}</code></dd>
          <dt>계획 증거 (plan)</dt><dd><code>{_esc(goal['plan_evidence']['id'])}</code> ({_esc(goal['plan_evidence']['label'])})</dd>
        </dl>
      </div>
      <div class="card">
        <h3>2. 책임 소유자 (Owner)</h3>
        <p>{_badge_html(goal['owner_badge'], goal['owner_badge_kind'])}</p>
        <dl class="kv-grid">
          <dt>기록된 소유자</dt><dd><code>{_esc(goal.get('current_owner'), '미지정 (null)')}</code></dd>
          <dt>수락 체인 검증 소유자</dt><dd><code>{_esc(goal.get('verified_accepted_owner'), '없음 (null)')}</code></dd>
          <dt>현 범위 수락 상태</dt><dd><code>{_esc(goal.get('owner_acceptance'))}</code> (체인은 <code>{"accepted" if goal.get('scope_accepted') else "pending"}</code>)</dd>
        </dl>
      </div>
      <div class="card">
        <h3>3. 출처 해시 및 시각 (Provenance)</h3>
        <dl class="kv-grid">
          <dt>입력 레코드 경로</dt><dd><code>{_esc(snap.get('record_path'), '메모리/표준입력')}</code></dd>
          <dt>레코드 SHA-256</dt><dd><code>{_esc(snap.get('record_sha256'), '미상')}</code></dd>
          <dt>캡처 시각 (제공 시)</dt><dd><code>{captured_display}</code></dd>
          <dt>스냅샷 생성 시각</dt><dd><code>{_esc(snap.get('generated_at'))}</code></dd>
        </dl>
      </div>
      <div class="card">
        <h3>4. 검증 단계 요약 및 토큰</h3>
        <dl class="kv-grid">
          <dt>실행 정산 성공</dt><dd><code>{counts['execution_succeeded']} / {counts['tasks_total']}</code></dd>
          <dt>독립 기술 검증 통과</dt><dd><code>{counts['technical_passed']} / {counts['tasks_total']}</code></dd>
          <dt>상위 통합 통과</dt><dd><code>{counts['parent_integration_passed']} / {counts['tasks_total']}</code></dd>
          <dt>전체 목표 최종 승인</dt><dd>{_badge_html(overall['badge'], overall['badge_kind'])}</dd>
          <dt>원시 토큰 합계</dt><dd><code>{_esc(usage['total_display'])}</code></dd>
        </dl>
      </div>
    </div>
  </header>

  <section class="section-card" id="decisions">
    <h2>필요한 의사결정 · 차단 요인 및 일관성 오류 ({len(decisions)}건)</h2>
    {decisions_table}
  </section>

  <section class="section-card" id="goal-ownership">
    <h2>목표 소유권 체인 및 전체 목표 최종 승인 분리</h2>
    <div class="grid-2">
      <div>
        <h3>소유권 이전 체인 (<code>$.ownership</code>)</h3>
        <p class="small muted">제안(<code>proposed</code>)이나 실행 터미널·상위 작업자로부터 소유자를 추론하지 않습니다. 오직 유효한 수락(<code>accepted</code>) 체인만 책임을 이전합니다.</p>
        {ownership_table}
        {proposals_html}
      </div>
      <div>
        <h3>전체 목표 최종 승인 (<code>$.goal.assessment</code>)</h3>
        <p>{_badge_html(overall['badge'], overall['badge_kind'])}</p>
        <p class="small muted">{_esc(overall['separation_note'])}</p>
        {assess_html}
      </div>
    </div>
  </section>

  <section class="section-card" id="tasks-stages">
    <h2>작업별 현재 시도(Dispatch) · 후보(Candidate) 및 3단계 검증 분리 ({len(tasks)}건)</h2>
    <p class="small muted">1단계(실행 정산), 2단계(독립 기술 검증), 3단계(상위 통합)와 전체 목표 최종 승인을 별도 열로 분리합니다. 구버전 후보·시도 바인딩이나 무효 증거는 성공 배지를 받을 수 없습니다.</p>
    {tasks_table_html}
    {''.join(task_details)}
  </section>

  <section class="section-card" id="unknowns-usage">
    <h2>미상 항목(Unknowns) 및 원시 토큰 사용량 (<code>$.usage</code>)</h2>
    <div class="grid-2">
      <div>
        <h3>명시적 미상 항목 ({len(unknowns)}건)</h3>
        <ul>{unknown_items}</ul>
      </div>
      <div>
        <h3>원시 토큰 사용량</h3>
        <dl class="kv-grid">
          <dt>관측 범위 (coverage)</dt><dd><code>{_esc(usage['coverage'])}</code></dd>
          <dt>기대 단위 / 기록 엔트리</dt><dd><code>{usage['expected_count']}</code> / <code>{usage['entry_count']}</code></dd>
          <dt>전체 원시 토큰 합계</dt><dd><strong><code>{_esc(usage['total_display'])}</code></strong></dd>
          <dt>토크나이저 유의사항</dt><dd>{_esc(usage['tokenizer_note'])}</dd>
        </dl>
        {f'<p class="small muted">레코드 메모: {_esc(usage["usage_note"])}</p>' if usage['usage_note'] else ''}
        <h4>공급자·토크나이저별 관측 부분합 (전체 추정치 아님)</h4>
        {subtotals_html}
      </div>
    </div>
  </section>

  <section class="section-card" id="evidence">
    <h2>증거 계보 및 해시 핀 목록 (<code>$.evidence</code> · {len(evidence_list)}건)</h2>
    <details class="detail-card" {"open" if not check['ok'] else ""}>
      <summary>전체 증거 참조·SHA-256·파일 대조 상태 펼치기 ({len(evidence_list)}건)</summary>
      <div class="detail-body">
        {ev_table}
      </div>
    </details>
  </section>
</main>
</body>
</html>
"""


def _validate_input_file(path):
    p = Path(path)
    if not p.exists():
        raise ValueError(f'Input file does not exist: {p}')
    if not p.is_file():
        raise ValueError(f'Input path is not a regular file: {p}')
    return p


def _write_exclusive_output(path, content, input_path=None):
    out = Path(path)
    if input_path is not None and out.resolve() == Path(input_path).resolve():
        raise ValueError(f'Output path cannot equal input path: {out}')
    parent = out.parent
    if not parent.exists() or not parent.is_dir():
        raise ValueError(f'Output parent directory does not exist: {parent}')
    with out.open('x', encoding='utf-8') as handle:
        handle.write(content)


def run_cases(suite, base):
    """Run synthetic status-view counterexample suite deterministically."""
    if not isinstance(suite, dict) or suite.get('version') != 1 or suite.get('label') != 'synthetic':
        return {
            'ok': False,
            'label': 'synthetic',
            'errors': [{'path': '$', 'code': 'suite_header', 'message': 'Expected version=1, label=synthetic'}],
            'cases': [],
        }
    raw_cases = suite.get('cases')
    if not isinstance(raw_cases, list) or not raw_cases:
        return {
            'ok': False,
            'label': 'synthetic',
            'errors': [{'path': '$.cases', 'code': 'empty_cases', 'message': 'At least one case is required'}],
            'cases': [],
        }
    results = []
    for idx, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            results.append({'name': f'case-{idx}', 'passed': False, 'failures': ['Case entry must be an object']})
            continue
        name = item.get('name', f'case-{idx}')
        rec = item.get('record')
        view = build_view(
            rec,
            base=base,
            record_path=f'synthetic://{name}/record.json',
            record_sha256='0' * 64,
            captured_at=item.get('captured_at'),
            generated_at='2026-10-27T00:00:00+09:00',
            require_routing=bool(item.get('require_routing', False)),
            require_resources=bool(item.get('require_resources', False)),
        )
        rendered = render_html(view)
        failures = []
        if 'expected_check_ok' in item and view['snapshot']['consistency_check']['ok'] != item['expected_check_ok']:
            failures.append(f"consistency_check.ok={view['snapshot']['consistency_check']['ok']} != {item['expected_check_ok']}")
        if 'expected_error_codes' in item:
            found_codes = sorted({e['code'] for e in view['snapshot']['consistency_check']['errors']})
            exp_codes = sorted(set(item['expected_error_codes']))
            if found_codes != exp_codes:
                failures.append(f'error_codes={found_codes} != {exp_codes}')
        if 'expected_overall_success' in item and view['summary']['earned_overall_success'] != item['expected_overall_success']:
            failures.append(f"earned_overall_success={view['summary']['earned_overall_success']} != {item['expected_overall_success']}")
        for sub in item.get('expected_html_contains', []):
            if sub not in rendered:
                failures.append(f'missing expected HTML substring: {sub!r}')
        for sub in item.get('expected_html_absent', []):
            if sub in rendered:
                failures.append(f'found forbidden HTML substring: {sub!r}')
        results.append({
            'name': name,
            'passed': not failures,
            'failures': failures,
            'check_ok': view['snapshot']['consistency_check']['ok'],
            'earned_overall_success': view['summary']['earned_overall_success'],
        })
    return {
        'ok': all(r['passed'] for r in results),
        'label': 'synthetic',
        'errors': [],
        'cases': results,
    }


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', dest='global_json', help='Print compact JSON view/result to stdout')
    sub = parser.add_subparsers(dest='command', required=True)

    render_p = sub.add_parser('render', help='Render a local static HTML snapshot (and optional compact JSON view) from record.json')
    render_p.add_argument('path', type=Path, help='Path to supplementary record.json')
    render_p.add_argument('--output', '-o', type=Path, help='Exclusive output path for HTML snapshot (never overwrites existing files)')
    render_p.add_argument('--json-output', type=Path, help='Exclusive output path for compact JSON view')
    render_p.add_argument('--json', action='store_true', help='Print compact JSON view to stdout')
    render_p.add_argument('--captured-at', help='Optional captured timestamp (reported only when supplied)')
    render_p.add_argument('--generated-at', help='Optional generation timestamp override')
    render_p.add_argument('--require-routing', action='store_true', help='Require a routing decision on every task')
    render_p.add_argument('--require-resources', action='store_true', help='Require resource_accounting="required"')

    cases_p = sub.add_parser('cases', help='Run synthetic status-view counterexample suite')
    cases_p.add_argument('path', type=Path, help='Path to status-view-cases.json')
    cases_p.add_argument('--json', action='store_true', help='Print JSON suite result')
    return parser


def main(argv=None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] not in ('render', 'cases', '-h', '--help', '--json'):
        raw_argv = ['render', *raw_argv]
    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    try:
        input_path = _validate_input_file(args.path)
    except ValueError as exc:
        err_payload = {'ok': False, 'errors': [{'path': str(args.path), 'code': 'input_read', 'message': str(exc)}]}
        print(json.dumps(err_payload, ensure_ascii=False, indent=2))
        return 2

    value, read_error, digest = record_check.read_json_snapshot(input_path)
    if read_error is not None:
        print(json.dumps({'ok': False, 'errors': [read_error]}, ensure_ascii=False, indent=2))
        return 2

    if args.command == 'cases':
        result = run_cases(value, input_path.parent)
        if args.global_json or args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print('PASS' if result['ok'] else 'FAIL')
            for c in result.get('cases', []):
                print(('PASS ' if c['passed'] else 'FAIL ') + str(c['name']))
                for f in c.get('failures', []):
                    print('  - ' + str(f))
        return 0 if result['ok'] else 1

    view = build_view(
        value,
        base=input_path.parent,
        record_path=input_path,
        record_sha256=digest,
        captured_at=args.captured_at,
        generated_at=args.generated_at,
        require_routing=args.require_routing,
        require_resources=args.require_resources,
    )
    html_text = render_html(view)
    json_text = json.dumps(view, ensure_ascii=False, indent=2) + '\n'

    try:
        if args.output is not None and args.json_output is not None and args.output.resolve() == args.json_output.resolve():
            raise ValueError('HTML and JSON output paths must be distinct')
        if args.output is not None:
            _write_exclusive_output(args.output, html_text, input_path=input_path)
        if args.json_output is not None:
            _write_exclusive_output(args.json_output, json_text, input_path=input_path)
    except (OSError, ValueError) as exc:
        err_payload = {'ok': False, 'errors': [{'path': str(args.output or args.json_output), 'code': 'output_write', 'message': str(exc)}]}
        print(json.dumps(err_payload, ensure_ascii=False, indent=2))
        return 2

    if args.global_json or args.json:
        sys.stdout.write(json_text)
    elif args.output is None and args.json_output is None:
        sys.stdout.write(html_text)
    else:
        summary_out = {
            'ok': view['snapshot']['consistency_check']['ok'],
            'earned_overall_success': view['summary']['earned_overall_success'],
            'record_sha256': digest,
            'output': str(args.output) if args.output is not None else None,
            'json_output': str(args.json_output) if args.json_output is not None else None,
            'next_unresolved': view['summary']['next_unresolved'],
        }
        print(json.dumps(summary_out, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
