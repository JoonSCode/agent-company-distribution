#!/usr/bin/env python3
"""Company read-only terminal view with explicit new planning-context capture."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import select
import signal
import sys
import termios
import time
import tty
import unicodedata

if __name__ == '__main__':
    sys.pycache_prefix = os.path.join(os.path.abspath(os.path.expanduser('~')), '.cache', 'agent-company', 'python')
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_tui_data import InputError, load_snapshot
from status_tui_input import load_record_snapshot
from status_tui_context import capture_context
import status_tui_graph as graph
import status_tui_navigation as navigation
import status_tui_wide as wide

MODES = ('org', 'flow', 'combined')


def clean(value):
    """Strip all terminal controls/bidi formatting, including untrusted C1 escapes."""
    return ''.join(char if char.isprintable() and unicodedata.category(char) not in {'Cc', 'Cf', 'Cs'} else '?'
                   for char in str(value))


def cell_width(value):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in value)


def fit(value, width):
    value = clean(value)
    if cell_width(value) <= width: return value
    result, cells = [], 0
    for char in value:
        size = cell_width(char)
        if cells + size > max(0,width-1): break
        result.append(char); cells += size
    return ''.join(result) + ('~' if width else '')


def pad(value, width):
    value = fit(value, width)
    return value + ' ' * max(0,width-cell_width(value))


def ascii_text(value):
    return ''.join(c if ord(c) < 128 else '?' for c in value)


def _actor(value):
    if value is None: return '?'
    if not value.get('actor'): return '?'
    actor = value['actor']
    return str(actor) + ('?' if value.get('acceptance') == 'unknown' else '*')


def _head(snapshot):
    org = snapshot['organization']
    if org is None: return '회사 | 조직 미기록 (registry는 roster 아님)'
    return ('회사 head: ' + _actor(org['head']) + ' | teams:' + ','.join(t['id'] for t in org['teams']) +
            ' | claimed (? 수락 미확인)')


def _team_lines(team, combined=True):
    if team is None: return ['[unassigned] 소속 미기록']
    title = '[' + team['id'] + '] ' + team['label']
    if not combined: return [title]
    return [title + ' | lead:' + _actor(team['lead']),
            '  member:' + (', '.join(_actor(m) for m in team['members']) or '?') +
            ' | 소속 ' + ('claimed' if team['members'] and all(m['basis'] == 'claimed' for m in team['members']) else 'unknown')]


def _org_pages(snapshot, width, height):
    # Organization remains a different relation, never a task prerequisite tree.
    org = snapshot['organization']
    blocks = [[_head(snapshot)]]
    for team in (org or {}).get('teams', []):
        if not team['members']:
            blocks.append(_team_lines(team))
        for member in team['members']:
            blocks.append(['['+team['id']+'] '+team['label']+' | lead:'+_actor(team['lead']),
                           '  member:'+_actor(member)+' | '+member['basis']+', no task edge'])
    room = max(1, height-5)
    pages, current = [], []
    for block in blocks:
        if len(block) > room:
            if current: pages.append(current); current=[]
            pages.extend(block[start:start+room] for start in range(0,len(block),room))
        elif len(current)+len(block) > room:
            pages.append(current); current=list(block)
        else:
            current.extend(block)
    if current: pages.append(current)
    return pages or [[]]


def _legacy_page_count(snapshot, width, height, mode='combined'):
    if mode not in MODES: raise ValueError('unsupported mode')
    if height < 7: return 1  # Enlarge-only, not phantom inaccessible task pages.
    if mode == 'org': return len(_org_pages(snapshot,max(1,width-1),height))
    return len(graph.layout(snapshot,max(1,width-1),max(1,height-1))['pages'])


def _style_spans(line, spans):
    """Apply cell-addressed presentation metadata after plain clipping."""
    result, position, active = [], 0, None
    for char in line:
        size = cell_width(char)
        if size:
            style = next((style for start, end, style in spans if start <= position < end), None)
            if style != active:
                if active is not None: result.append('\x1b[0m')
                if style is not None: result.append('\x1b[' + style + 'm')
                active = style
        result.append(char)
        position += size
    if active is not None: result.append('\x1b[0m')
    return ''.join(result)


def _legacy_frame(snapshot, width, height, mode='combined', page=0, color=False, *, ascii=False):
    """Pure cell-bounded product renderer; ASCII is an additive presentation seam."""
    if mode not in MODES: raise ValueError('unsupported mode')
    if type(width) is not int or type(height) is not int or min(width,height) < 1: raise ValueError('positive dimensions required')
    width, capacity = max(1,width-1), max(1,height-1)
    goal = snapshot['overall_goal_acceptance']
    error = snapshot.get('_refresh_error')
    failed = goal.get('badge_kind') == 'error' or not snapshot['check']['ok']
    goal_state = (('error' if failed else 'recorded pass' if goal['earned_success'] else 'pending') if ascii else
                  ('오류' if failed else '기록상 통과' if goal['earned_success'] else '확인 대기'))
    heading = ('Company ['+mode+'] ' + ('Goal: ' if ascii else '전체 목표: ') + goal_state +
               (' | User: unobserved' if ascii else ' | 사용자 확인: 미관측'))
    if error:
        heading = 'ERROR | last-good '+str(snapshot.get('_last_good_age',0))+'s | '+('stale' if ascii else '갱신 오류·오래된 화면')
    count = _legacy_page_count(snapshot,width+1,height,mode)
    index = max(0,page) % count
    names = {'org':'조직', 'flow':'작업 흐름', 'combined':'통합'}
    navigation = ((mode+' | o/f/c views n/p pages q exit') if ascii else
                  names[mode]+' | o/f/c 보기 n/p 쪽 q 종료') + ' | page:'+str(index+1)+'/'+str(count)
    if height < 7:
        # Exit comes first even when only one row is available. At 1x1 only q
        # fits; neither task navigation nor a complete map is promised.
        first = ('ERROR q exit' if error else 'q exit') if ascii else ('ERROR q 종료' if error else 'q 종료')
        if width == 1: first = 'q'
        lines = [first, 'Enlarge only' if ascii else '확대 필요', heading][:capacity]
        spans = [(0, 0, width, '1;31' if error else '1;39')]
    else:
        spans = [(0, 0, width, '1;31' if error or failed else '1;36')]
        if mode == 'org':
            body = _org_pages(snapshot,width,height)[index]
            if ascii: body = [graph.safe(line,True) for line in body]
            continuation = 'Registry is not staffing; org is not task DAG' if ascii else '조직 주장 · registry는 실시간 인원 아님 · 작업 간선과 별개'
        else:
            plan = graph.layout(snapshot,width,capacity)
            body = graph.draw_page(snapshot,plan,index,width,ascii)
            spans.extend((row+2, start, end, style) for row, start, end, style in graph.page_spans(snapshot,plan,index))
            continuation = graph.continuation(plan,index,ascii)
            if width < 35 or plan['room'] < plan['unit']:
                continuation = 'Enlarge for node map; n/p text slices' if ascii else '확대 필요 · n/p 작업/연결 정보'
        label = snapshot.get('input_label','unknown')
        synthetic = 'synthetic' in label or snapshot.get('record_label') == 'synthetic'
        coverage = snapshot.get('dependency_coverage')
        provenance = (('SYNTHETIC DEMO' if synthetic else 'Recorded claims') + ' | ' +
                      ('Partial links' if coverage == 'partial' else 'Links unknown') + ' | No live observation') if ascii else (
                      ('합성 시연' if synthetic else '기록된 주장') + ' | ' +
                      ('연결 일부만 기록' if coverage == 'partial' else '연결 정보 미확인') + ' | 실행 관측 없음')
        lines = [heading,navigation,*body,continuation,provenance]
    lines = [fit(graph.safe(line,ascii),width) for line in lines[:capacity]]
    if color and not ascii and 'NO_COLOR' not in os.environ:
        for i,line in enumerate(lines):
            lines[i] = _style_spans(line, [(start,end,style) for row,start,end,style in spans if row == i])
    return '\n'.join(lines)


def _provenance(snapshot, ascii=False):
    synthetic = 'synthetic' in snapshot.get('input_label', '') or snapshot.get('record_label') == 'synthetic'
    partial = snapshot.get('dependency_coverage') == 'partial'
    return ((('SYNTHETIC DEMO' if synthetic else 'Recorded claims') + ' | ' +
             ('Partial links' if partial else 'Links unknown') + ' | No live observation') if ascii else
            (('합성 시연' if synthetic else '기록된 주장') + ' | ' +
             ('연결 일부만 기록' if partial else '연결 정보 미확인') + ' | 실행 관측 없음'))


def _compact_provenance(snapshot, width, ascii=False):
    if cell_width(_provenance(snapshot, ascii)) <= width: return []
    synthetic = 'synthetic' in snapshot.get('input_label', '') or snapshot.get('record_label') == 'synthetic'
    partial = snapshot.get('dependency_coverage') == 'partial'
    words = (['SYNTHETIC' if synthetic else 'RECORDED', 'PART LINKS' if partial else 'LINKS ?', 'NO LIVE'] if ascii else
             ['합성 시연' if synthetic else '기록 주장', '연결 일부' if partial else '연결 불명', '관측 없음'])
    # Each essential qualifier fits even at the first usable width (11 cells).
    joined = ' | '.join(words)
    return [joined] if cell_width(joined) <= width else words


def _compact_org_pages(snapshot, width, room, ascii=False):
    rows = [part for page in _org_pages(snapshot, width, 10**9) for line in page
            for part in wide.wrap(graph.safe(line, ascii), width)]
    return navigation.text_pages(rows, room)


def _view(snapshot, width, height, layout, state, ascii):
    selected = snapshot['tasks'][0]['id'] if snapshot['tasks'] else ''
    current = navigation.reconcile(snapshot, state or navigation.State(layout=layout, selected=selected))
    provenance = _compact_provenance(snapshot, width - 1, ascii)
    room = min(height - 5, height - 3 - len(provenance)) if provenance else height - 5
    return navigation.plan(snapshot, current, max(1, width - 1), max(1, room), ascii)


def page_count(snapshot, width, height, mode='combined', *, layout='wide', state=None, ascii=False):
    if mode not in MODES: raise ValueError('unsupported mode')
    if layout not in ('wide', 'focus', 'legacy'): raise ValueError('unsupported layout')
    if height < 7 or width < 12: return 1
    provenance = _compact_provenance(snapshot, width - 1, ascii)
    if provenance and mode == 'org':
        return len(_compact_org_pages(snapshot, width - 1, max(1, min(height - 5, height - 3 - len(provenance))), ascii))
    if mode == 'org' or layout == 'legacy': return _legacy_page_count(snapshot, width, height, mode)
    return len(_view(snapshot, width, height, layout, state, ascii)['pages'])


def _compact_frame(snapshot, width, height, mode, page, layout, state, ascii, provenance):
    """Narrow usable screens paginate real information, never hide provenance."""
    W, H = width - 1, height - 1
    room = max(1, min(height - 5, height - 3 - len(provenance)))
    if mode == 'org':
        pages = _compact_org_pages(snapshot, W, room, ascii)
        index = max(0, page) % len(pages)
        body = pages[index]
        screen = 'org' if ascii else '조직'
        meta = {'kind': 'text', 'nodes': [], 'pages': len(pages), 'page': index}
    else:
        view = _view(snapshot, width, height, layout, state, ascii)
        index = navigation.page_index(view, None if state is not None else page)
        canvas, nodes = navigation.draw(snapshot, view, index, W, ascii)
        body = canvas.text().splitlines()
        screen = view['state'].screen if ascii else {'map': '지도', 'overview': '개요', 'regions': '구간',
                 'source': '원문', 'links': '연결', 'teams': '팀'}[view['state'].screen]
        meta = {'kind': view['kind'], 'nodes': nodes, 'pages': len(view['pages']), 'page': index,
                'state': {key: value for key, value in vars(view['state']).items() if key != 'history'}}
        if view['kind'] == 'summary':
            boxes = view['pages'][index]['boxes']
            aggregates = view['pages'][index]['aggregates']
            meta.update(summary_regions=[{**card, 'box': boxes[card['region']]} for card in view['cards'] if card['region'] in boxes],
                        aggregate_edges=aggregates,
                        undrawn_aggregate_edges=[edge for edge in view['aggregates'] if edge not in aggregates],
                        selection_count=len(view['cards']))
    canvas = wide.Canvas(W, H)
    failed = snapshot['overall_goal_acceptance'].get('badge_kind') == 'error' or not snapshot['check']['ok']
    label = ('ERROR ' if failed or snapshot.get('_refresh_error') else '') + screen + ' ' + str(index + 1) + '/' + str(meta['pages'])
    canvas.put(0, 0, fit(label, W), 'title')
    for y, row in enumerate(body): canvas.put(0, y + 1, row)
    for y, row in enumerate(provenance): canvas.put(0, H - 1 - len(provenance) + y, row, 'accent')
    # Quit is first. Only advertise controls that exist on this usable surface.
    footer = ('q exit' if ascii else 'q 종료') + (' n/p' if W < 20 or mode == 'org' else ' n/p j/k b l s')
    canvas.put(0, H - 1, footer, 'accent')
    meta.update(body_rows=room, body_offset=1, compact_provenance=provenance)
    return canvas.text(), meta


def render_details(snapshot, width, height, mode='combined', page=0, color=False, *, ascii=False,
                   layout='wide', state=None, palette='light'):
    """Frame and emitted-cell metadata from the actual default product surface."""
    if mode not in MODES: raise ValueError('unsupported mode')
    if layout not in ('wide', 'focus', 'legacy'): raise ValueError('unsupported layout')
    if type(width) is not int or type(height) is not int or min(width, height) < 1:
        raise ValueError('positive dimensions required')
    if palette not in wide.PALETTES: raise ValueError('unsupported palette')
    if height < 7 or width < 12:
        error = snapshot.get('_refresh_error')
        first = ('ERROR q exit' if error else 'q exit') if ascii else ('ERROR q 종료' if error else 'q 종료')
        if width < 12: first = 'q'
        lines = [first, 'Enlarge only' if ascii else '확대 필요'][:max(1, height - 1)]
        return '\n'.join(fit(line, max(1, width - 1)) for line in lines), {'kind': 'enlarge', 'nodes': [], 'pages': 1}
    compact = _compact_provenance(snapshot, width - 1, ascii)
    if compact and (layout != 'legacy' or mode == 'org'):
        return _compact_frame(snapshot, width, height, mode, page, layout, state, ascii, compact)
    if mode == 'org' or layout == 'legacy':
        return _legacy_frame(snapshot, width, height, mode, page, color, ascii=ascii), {'kind': 'legacy', 'nodes': []}
    view = _view(snapshot, width, height, layout, state, ascii)
    index = navigation.page_index(view, None if state is not None else page)
    current = view['state']
    body, nodes = navigation.draw(snapshot, view, index, width - 1, ascii)
    W, H = width - 1, height - 1
    canvas = wide.Canvas(W, H)
    goal = snapshot['overall_goal_acceptance']
    failed = goal.get('badge_kind') == 'error' or not snapshot['check']['ok']
    goal_state = (('error' if failed else 'recorded pass' if goal['earned_success'] else 'pending') if ascii else
                  ('오류' if failed else '기록상 통과' if goal['earned_success'] else '확인 대기'))
    heading = 'Company [' + mode + '] ' + ('Goal: ' if ascii else '전체 목표: ') + goal_state + (
        ' | User: unobserved' if ascii else ' | 사용자 확인: 미관측')
    if snapshot.get('_refresh_error'):
        heading = 'ERROR | last-good ' + str(snapshot.get('_last_good_age', 0)) + 's | ' + ('stale' if ascii else '갱신 오류·오래된 화면')
    def text(y, value, role='secondary'):
        canvas.put(0, y, fit(graph.safe(value, ascii), W), role)
    text(0, heading, 'ERR' if snapshot.get('_refresh_error') or failed else 'accent')
    by_id = {task['id']: task for task in snapshot['tasks']}
    scope = current.scope + (':' + current.value if current.value else '')
    if not ascii:
        team_names = {team['id']: team['label'] for team in (snapshot.get('organization') or {}).get('teams', [])}
        scope = ('전체' if current.scope == 'all' else team_names.get(current.value, '소속 미확인') if current.scope == 'team'
                 else '구간 ' + str(int(current.value) + 1))
    team = graph.lane(snapshot, by_id[current.selected], ascii) if current.selected in by_id else ''
    screen_label = (current.screen + '/' + current.layout) if ascii else {
        'map': '넓은 지도' if current.layout == 'wide' else '초점 지도', 'overview': '전체 개요',
        'teams': '팀 선택', 'regions': '구간 선택', 'links': '이름 있는 연결', 'source': '원본·배정 근거'}[current.screen]
    label = (screen_label + (' | ' if ascii else ' · ') + scope + ' ' + ('선택 ' if not ascii else 'selected ') + team + ' | page:' +
             str(index + 1) + '/' + str(len(view['pages'])))
    # Current screen always names the actual applicable actions; f remains flow.
    keys = ('o/f/c n/p j/k x focus w wide v overview' if ascii else 'o/f/c n/p j/k x 초점 w 넓게 v 개요')
    text(1, label + ' | ' + keys)
    for y, row in enumerate(body.grid): canvas.grid[y + 2] = row.copy()
    visible = [route['edge'] for route in view['pages'][index]['routes']] if view['kind'] == 'map' else []
    hidden_tasks = len(snapshot['tasks']) - len(nodes)
    undrawn = len(graph.known_edges(snapshot)) - len(visible)
    if view['kind'] == 'map':
        continuation = ((f'Hidden {hidden_tasks} tasks/{undrawn} links; ' if ascii else
                         f'미표시 {hidden_tasks}작업/{undrawn}연결 · ') +
                        ('q exit l links s source t team r region b back' if ascii else 'q 종료 l 연결 s 원문 t 팀 r 구간 b 뒤로'))
        if not graph.known_edges(snapshot):
            continuation = ('Independence unknown; ' if ascii else '독립 여부 미확인 · ') + continuation
    else:
        continuation = ('q exit b back n/p pages j/k select Enter open l links s source' if ascii else
                        'q 종료 b 뒤로 n/p 쪽 j/k 선택 Enter 진입 l 연결 s 원문')
        if current.screen == 'source':
            continuation = 'q exit b back n/p source pages' if ascii else 'q 종료 b 뒤로 n/p 원문 쪽'
        elif view['kind'] == 'summary':
            undrawn = len(view['aggregates']) - len(view['pages'][index]['aggregates'])
            continuation = (f'q exit; aggregate != task path; {undrawn} undrawn; j/k Enter map b back l links' if ascii else
                            f'q 종료 · 집계≠개별경로 · 미표시 {undrawn}집계 · j/k 선택 Enter 지도 b 뒤로 l 연결')
    if view['room'] < 5 and current.screen == 'map':
        continuation = 'q exit; n/p task/link info; enlarge' if ascii else 'q 종료 · n/p 작업/연결 정보 · 확대 필요'
    text(H - 2, continuation)
    provenance = _provenance(snapshot, ascii)
    text(H - 1, provenance, 'accent')
    meta = {'kind': view['kind'], 'nodes': nodes, 'page': index, 'pages': len(view['pages']),
            'map_columns': view.get('columns'), 'exact_visible_edges': visible,
            'undrawn_edges': [edge for edge in graph.known_edges(snapshot) if edge not in visible],
            'hidden_tasks': hidden_tasks, 'body_rows': view['room'], 'body_offset': 2,
            'state': {key: value for key, value in vars(current).items() if key != 'history'}}
    if view['kind'] == 'summary':
        boxes = view['pages'][index]['boxes']
        aggregates = view['pages'][index]['aggregates']
        meta.update(summary_regions=[{**card, 'box': boxes[card['region']]} for card in view['cards'] if card['region'] in boxes],
                    aggregate_edges=aggregates,
                    undrawn_aggregate_edges=[edge for edge in view['aggregates'] if edge not in aggregates],
                    selection_count=len(view['cards']))
    return canvas.text(color and not ascii, palette), meta


def render_frame(snapshot, width, height, mode='combined', page=0, color=False, *, ascii=False,
                 layout='wide', state=None, palette='light'):
    return render_details(snapshot, width, height, mode, page, color, ascii=ascii,
                          layout=layout, state=state, palette=palette)[0]


class RefreshState:
    """Bounded read-only refresh. A rejected candidate cannot mutate last-good."""
    def __init__(self, manifest, interval: float = 1, *, record=False, metadata=None, context=None):
        if not math.isfinite(interval) or interval < .25: raise ValueError('interval must be finite and >=0.25')
        self.manifest, self.interval = manifest, interval
        self.record, self.metadata, self.context = record, metadata, context
        self.snapshot, self.error, self.fingerprint = None, None, None
        self.last_good_at, self.next_read, self.idle = None, 0, interval

    def refresh(self, now):
        if now < self.next_read: return False
        old_error = self.error
        try:
            incoming = (load_record_snapshot(self.manifest, self.metadata, context_path=self.context) if self.record
                        else load_snapshot(self.manifest))
            comparable = {k:v for k,v in incoming.items() if k != 'generated_at'}
            digest = hashlib.sha256(json.dumps(comparable,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
            changed = digest != self.fingerprint
            if changed: self.snapshot = incoming
            self.fingerprint, self.error, self.last_good_at = digest, None, now
            self.idle = self.interval if changed or old_error else min(5,max(self.interval,self.idle*2))
            self.next_read = now+self.idle
            return changed or old_error is not None
        except (InputError,OSError) as exc:
            self.error = type(exc).__name__
            self.idle = self.interval
            self.next_read = now+5
            return old_error != self.error


def _size(fd):
    size = os.get_terminal_size(fd)
    return max(1,size.columns),max(1,size.lines)


def _restore_terminal(fd, before):
    termios.tcsetattr(fd, termios.TCSANOW, before)
    # Darwin can set PENDIN on cbreak -> canonical even when tcsetattr was
    # given the original clear bit. A second tcsetattr does not clear it.
    # Flush only that newly introduced pending-input state; never clear an
    # original PENDIN=1. Keep every original typed cc value unmodified.
    pendin = getattr(termios, 'PENDIN', 0)
    if sys.platform == 'darwin' and pendin and not before[3] & pendin:
        if termios.tcgetattr(fd)[3] & pendin:
            termios.tcflush(fd, termios.TCIFLUSH)


def run(args):
    if not (sys.stdin.isatty() and sys.stdout.isatty()) or os.ttyname(0) != os.ttyname(1):
        raise InputError('persistent mode requires the same caller-owned input/output PTY')
    if os.environ.get('TERM') in (None,'','dumb','unknown'):
        raise InputError('terminal lacks a supported persistent cursor surface')
    refresh = RefreshState(args.record or args.manifest,args.interval,
                           record=args.record is not None,metadata=args.metadata,context=args.context)
    refresh.refresh(time.monotonic())
    if refresh.snapshot is None: raise InputError('initial input rejected')
    before = termios.tcgetattr(0)
    previous_handlers = {}
    stop, dirty, resize = False, True, False
    page, mode, painted, next_paint = 0,args.mode,None,0
    state = navigation.State(layout=args.layout,
                             selected=refresh.snapshot['tasks'][0]['id'] if refresh.snapshot['tasks'] else '')
    def stopping(*_):
        nonlocal stop
        stop = True
    def resized(*_):
        nonlocal resize
        resize = True
    try:
        for sig, handler in [(signal.SIGTERM,stopping),(signal.SIGINT,stopping),(signal.SIGWINCH,resized)]:
            previous_handlers[sig] = signal.signal(sig,handler)
        tty.setcbreak(0,termios.TCSANOW)
        sys.stdout.write('\x1b[?1049h\x1b[?25l'); sys.stdout.flush()
        while not stop:
            now = time.monotonic()
            if refresh.refresh(now): dirty=True
            if resize: dirty=True; resize=False
            snapshot = refresh.snapshot
            if refresh.error:
                snapshot = {**snapshot, '_refresh_error':refresh.error,
                            '_last_good_age':int(max(0,now-(refresh.last_good_at or now)))//5*5}
                dirty = True  # frame equality suppresses unchanged error-age repaints
            if dirty and now >= next_paint:
                width,height = _size(1)
                state = navigation.reconcile(snapshot, state)
                if mode == 'org' or args.layout == 'legacy':
                    page %= page_count(snapshot,width,height,mode,layout=args.layout,ascii=args.ascii)
                frame = render_frame(snapshot,width,height,mode,page,color=not args.no_color and not args.ascii,
                                     ascii=args.ascii,layout=args.layout,
                                     state=None if mode == 'org' or args.layout == 'legacy' else state,
                                     palette=args.palette)
                if frame != painted:
                    sys.stdout.write('\x1b[H\x1b[2J'+frame.replace('\n','\r\n')); sys.stdout.flush()
                    painted=frame; next_paint=time.monotonic()+.25
                dirty=False
            timeout = min(.5,max(.01,refresh.next_read-time.monotonic()))
            if dirty: timeout=min(timeout,max(.01,next_paint-time.monotonic()))
            if select.select([0],[],[],timeout)[0]:
                keys=os.read(0,64)
                if not keys: break
                for key in keys:
                    if key in (ord('q'),3): stop=True
                    elif key in (ord('o'),ord('f'),ord('c')):
                        mode={ord('o'):'org',ord('f'):'flow',ord('c'):'combined'}[key]; page=0; dirty=True
                        state.screen='map'; state.page=0
                    elif key in (ord('n'),ord('p')) and (mode == 'org' or args.layout == 'legacy'):
                        count=page_count(refresh.snapshot,*_size(1),mode,layout=args.layout,ascii=args.ascii)
                        page=(page+(1 if key==ord('n') else -1))%count; dirty=True
                    elif args.layout != 'legacy' and key in b'jkxwvtrlsbnp\r\n':
                        mode = 'combined' if mode == 'org' else mode
                        state = navigation.transition(refresh.snapshot,state,'enter' if key in (10,13) else chr(key))
                        dirty=True
        return 0
    finally:
        try: _restore_terminal(0,before)
        finally:
            try:
                reset = '\x1b[0m' if not args.no_color and not args.ascii and 'NO_COLOR' not in os.environ else ''
                sys.stdout.write(reset+'\x1b[?25h\x1b[?1049l'); sys.stdout.flush()
            finally:
                for sig,handler in previous_handlers.items(): signal.signal(sig,handler)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--manifest',type=Path,help='strict source-pinned manifest-v1 attachment')
    inputs.add_argument('--record',type=Path,help='explicit ordinary Company record; observe current bytes each refresh')
    parser.add_argument('--metadata',type=Path,help='optional immutable manifest-v1 enrichment; requires --record')
    parser.add_argument('--context',type=Path,help='immutable captured planning context; requires --record')
    parser.add_argument('--capture-context',type=Path,help='explicitly capture --record/--metadata to a NEW private file, then exit')
    parser.add_argument('--mode',choices=MODES,default='combined')
    parser.add_argument('--layout',choices=('wide','focus','legacy'),default='wide',help='viewport-filled cards; focus is optional; legacy preserves old slices')
    parser.add_argument('--palette',choices=('light','dark'),default='light',help='local colors only; inherits terminal background/font')
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--width',type=int)
    parser.add_argument('--height',type=int)
    parser.add_argument('--interval',type=float,default=1)
    parser.add_argument('--no-color',action='store_true')
    parser.add_argument('--ascii',action='store_true')
    args=parser.parse_args(argv)
    if args.metadata is not None and args.record is None: parser.error('--metadata requires --record')
    if args.context is not None and (args.record is None or args.metadata is not None):
        parser.error('--context requires --record and excludes --metadata')
    if args.capture_context is not None and (args.record is None or args.metadata is None or args.context is not None or args.once or args.json):
        parser.error('--capture-context requires --record/--metadata only, without --context/--once/--json')
    if not math.isfinite(args.interval) or args.interval < .25: parser.error('--interval must be finite and >=0.25')
    if not args.once and (args.json or args.width is not None or args.height is not None):
        parser.error('--json/--width/--height require --once; persistent mode uses its PTY size')
    if (args.width is not None and args.width < 1) or (args.height is not None and args.height < 1): parser.error('positive dimensions required')
    try:
        if args.capture_context is not None:
            print(json.dumps(capture_context(args.record,args.metadata,args.capture_context),ensure_ascii=False))
            return 0
        if args.once:
            snapshot=(load_record_snapshot(args.record,args.metadata,context_path=args.context) if args.record is not None
                      else load_snapshot(args.manifest))
            if args.json: print(json.dumps(snapshot,ensure_ascii=False,indent=2))
            else:
                frame=render_frame(snapshot,args.width or 80,args.height or 12,args.mode,ascii=args.ascii,
                                   layout=args.layout,palette=args.palette)
                print(frame)
            return 0
        return run(args)
    except (InputError,OSError,ValueError) as exc:
        # Do not echo arbitrary source values, raw transcripts, paths or secrets.
        print('Company TUI: invalid input or unsupported terminal ('+type(exc).__name__+')',file=sys.stderr)
        return 2


if __name__ == '__main__': sys.exit(main())
