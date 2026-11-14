"""Pure, bounded task-map presentation; no file/host/model/assignment operations.

Small connected slices avoid crossing ambiguity. Every recorded edge has a
numbered, reachable slice (possibly shared with the primary task slice). Stable
@N references follow input order, never task state or a guessed execution order.
"""
from __future__ import annotations

import unicodedata

STATES = {'ACC': '작업 검토 통과', 'SUB': '제출·검토 대기', 'WAIT': '선행 작업 대기',
          'FAIL': '단계 검증 오류', 'ERR': '작업 기록 오류', '?': '상태 미확인'}
EN_STATES = {'ACC': 'Task review passed', 'SUB': 'Submitted; review due',
             'WAIT': 'Prerequisites pending', 'FAIL': 'Stage validation error',
             'ERR': 'Task record error', '?': 'State unknown'}
# Only state-bound spans receive semantic color; source words never choose it.
STATE_STYLES = {'ACC': '32', 'SUB': '33', 'WAIT': '33', 'FAIL': '1;31',
                'ERR': '1;31', '?': '39'}
CLASSES = dict(zip(('general', 'language', 'structured_data', 'reasoning', 'code', 'research',
                    'visual', 'design', 'media_generation', 'tool_use'),
                   ('일반', '언어', '구조화 데이터', '추론', '코드', '조사', '시각', '설계',
                    '미디어 생성', '도구 활용')))
EN_CLASSES = dict(zip(CLASSES, ('general', 'language', 'data', 'reasoning', 'code', 'research',
                               'visual', 'design', 'media gen', 'tool use')))
# Exact approved profile id/name/native_agent.name triples; presentation only.
SPECIALISTS = {'agent-company-founder': '창업 전문가', 'agent-company-planning': '기획 전문가',
               'agent-company-development': '개발 전문가', 'agent-company-design': '디자인 전문가',
               'agent-company-marketing': '마케팅 전문가', 'agent-company-qa-release': 'QA·출시 전문가'}


def clean(value):
    return ''.join(c if c.isprintable() and unicodedata.category(c) not in {'Cc', 'Cf', 'Cs'} else '?'
                   for c in str(value))


def cells(value):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in 'WF' else 1
               for c in value)


def fit(value, width):
    value = clean(value)
    if cells(value) <= width:
        return value
    result, used = [], 0
    for c in value:
        size = cells(c)
        if used + size > max(0, width - 1):
            break
        result.append(c)
        used += size
    return ''.join(result) + ('~' if width else '')


def pad(value, width):
    value = fit(value, width)
    return value + ' ' * max(0, width - cells(value))


def safe(value, ascii=False):
    value = clean(value)
    return ''.join(c if ord(c) < 128 else '?' for c in value) if ascii else value


def model_label(task, ascii=False):
    model, basis = task.get('assigned_model'), task.get('model_basis')
    if not model or basis not in ('assigned', 'planned'):
        return 'Model unknown' if ascii else '모델 미확인'
    # Explicit legacy/demo aliases only; arbitrary short custom IDs stay exact.
    if model in ('m1', 'fixture-model'):
        return (('Model name unknown; planned ID:' if basis == 'planned' else 'Model name unknown; assigned ID:') if ascii else
                ('모델명 미확인 · 계획 ID:' if basis == 'planned' else '모델명 미확인 · 할당 ID:')) + model
    return (('Planned: ' if basis == 'planned' else 'Assigned: ') if ascii else
            ('계획: ' if basis == 'planned' else '할당: ')) + safe(model, ascii)


def specialist_label(task, ascii=False):
    specialist = task.get('specialist', {})
    status, identity = specialist.get('status'), specialist.get('id')
    if status == 'none':
        return 'Specialist none' if ascii else '전문가 없음'
    if status != 'assigned' or not identity:
        return 'Specialist unknown' if ascii else '전문가 미확인'
    if identity in SPECIALISTS:
        return ('Specialist: ' + identity.removeprefix('agent-company-') if ascii else SPECIALISTS[identity])
    return ('Specialist label unavailable: ' if ascii else '전문가명 미확인: ') + safe(identity, ascii)


def state_class(task, ascii=False):
    classification = task.get('classification')
    return ((EN_STATES if ascii else STATES).get(task.get('state'), EN_STATES['?'] if ascii else STATES['?']),
            (EN_CLASSES.get(classification, 'class?') if ascii else CLASSES.get(classification, '분류 미확인')))


def task_fields(task, ref, inner, split, ascii=False):
    identity = safe(task['id'], ascii)
    identity = identity if cells(identity) <= 10 else 'ID~'
    title = safe(task.get('title') or '?', ascii)
    if title == '?':
        title = 'Title unknown' if ascii else '제목 미확인'
    state, classification = state_class(task, ascii)
    return [ref + ' ' + identity + ' ' + title, *([state, classification] if split else
            [state + (' | ' if ascii else ' · ') + classification]),
            model_label(task, ascii), specialist_label(task, ascii)]


def known_edges(snapshot):
    return [(p, t['id']) for t in snapshot['tasks'] for p in t.get('needs', [])]


def layout(snapshot, width, height):
    """Return deterministic geometry and edge-page routes, independent of status.

    width/height are usable cells/rows AFTER the caller's reserved row/column.
    Each page: nodes (id,x,y,width,height), edges (source,target), kind.
    Lane headers are at node.y; the bordered node starts at node.y+1.
    """
    tasks = snapshot['tasks']
    by_id = {t['id']: t for t in tasks}
    refs = {t['id']: '@' + str(i+1) for i, t in enumerate(tasks)}
    teams = (snapshot.get('organization') or {}).get('teams', [])
    order = [t['id'] for team in teams for t in tasks if t.get('team_id') == team['id']]
    order += [t['id'] for t in tasks if t['id'] not in set(order)]
    edges = known_edges(snapshot)
    if height < 6:
        # No task-page accessibility claim at an enlarge-only physical size.
        return {'pages': [{'kind': 'enlarge', 'nodes': [], 'edges': []}],
                'refs': refs, 'node_pages': {}, 'edge_pages': {}, 'edges': edges}
    # Reserve overview, navigation, continuation and provenance.
    room = max(1, height - 4)
    columns = 2 if width >= 79 else 1
    node_width = (width - 3) // 2 if columns == 2 else width
    inner = max(1, node_width - 4)
    # Worst-case labels, not the current state, fix geometry during refresh.
    split = any(cells(state + ' · ' + CLASSES.get(t.get('classification'), '분류 미확인')) > inner
                for t in tasks for state in STATES.values())
    # English is deliberately split at this width to preserve whole state words.
    unit = 8 if split else 7
    pages = []
    node_pages = {}
    edge_pages = {}

    def add(ids, selected, shape='pair'):
        nodes = []
        if len(ids) == 3:
            if shape == 'fanin':
                positions = [(0, 0), (0, unit), (node_width + 3, unit // 2)]
            else:
                positions = [(0, unit // 2), (node_width + 3, 0), (node_width + 3, unit)]
        else:
            positions = [(i * (node_width + 3), 0) for i in range(len(ids))]
        for identity, (x, y) in zip(ids, positions):
            nodes.append({'id': identity, 'x': x, 'y': y, 'width': node_width, 'height': unit - 1})
            node_pages.setdefault(identity, len(pages) + 1)
        pages.append({'kind': 'graph', 'nodes': nodes, 'edges': selected, 'split': split})
        for edge in selected:
            edge_pages.setdefault(tuple(edge), len(pages))

    if width < 35 or room < unit:
        # Short/narrow but usable: real n/p task/edge text slices (not tiny).
        for identity in order:
            task = by_id[identity]
            fields = [refs[identity] + ' ID: ' + safe(identity),
                      safe(task.get('title') or '제목 미확인'), *state_class(task),
                      model_label(task), specialist_label(task)]
            chunks = [fit(field, width) for field in fields]
            node_pages[identity] = len(pages) + 1
            for start in range(0, len(chunks), room):
                pages.append({'kind': 'text', 'lines': chunks[start:start+room], 'nodes': [], 'edges': [],
                              'task':identity, 'start':start, 'count':room})
        for source, target in edges:
            edge_pages[(source, target)] = len(pages) + 1
            pages.append({'kind': 'text', 'lines': [refs[source] + ' -> ' + refs[target]], 'nodes': [],
                          'edges': [(source, target)]})
    else:
        remaining = set(order)
        for identity in order:
            if identity not in remaining:
                continue
            outgoing = [b for a, b in edges if a == identity and b in remaining]
            incoming = [a for a, b in edges if b == identity and a in remaining]
            join = next((b for b in outgoing if sum(a in remaining for a,z in edges if z == b) >= 2), None)
            if columns == 2 and room >= unit * 2 and join:
                parents = [a for a,b in edges if b == join and a in remaining][:2]
                ids = [*parents, join]
                add(ids, [(a, join) for a in parents], 'fanin')
            elif columns == 2 and room >= unit * 2 and len(outgoing) >= 2:
                ids = [identity, *outgoing[:2]]
                add(ids, [(identity, b) for b in outgoing[:2]], 'fork')
            elif columns == 2 and room >= unit * 2 and len(incoming) >= 2:
                ids = [*incoming[:2], identity]
                add(ids, [(a, identity) for a in incoming[:2]], 'fanin')
            elif columns == 2 and (outgoing or incoming):
                ids = [identity, outgoing[0]] if outgoing else [incoming[0], identity]
                add(ids, [(ids[0], ids[1])])
            else:
                ids = [identity]
                # Co-visible disconnected nodes have NO decorative edge.
                other = next((i for i in order if i in remaining and i != identity and
                              (identity, i) not in edges and (i, identity) not in edges), None)
                if columns == 2 and other:
                    ids.append(other)
                add(ids, [])
            remaining.difference_update(ids)
        # Every remaining edge gets an explicit connected detail page when wide,
        # or a two-ended, page-addressed portal when narrow. No edge is dropped.
        for source, target in edges:
            if (source, target) in edge_pages:
                continue
            if columns == 2:
                add([source, target], [(source, target)])
            else:
                edge_pages[(source, target)] = len(pages) + 1
                pages.append({'kind': 'portal', 'nodes': [], 'edges': [(source, target)]})
    # Stack existing noncrossing slices, not a new graph layout. Each slice's
    # edges stay inside its own disjoint vertical extent. Recompute primary
    # references after packing, since every later page number may have moved.
    packed = []
    for page in pages:
        if page['kind'] == 'portal':
            continue  # Regenerated below in a compact complete edge directory.
        if page['kind'] == 'graph':
            extent = max(n['y'] + n['height'] + 1 for n in page['nodes'])
            previous = packed[-1] if packed else None
            used = max((n['y'] + n['height'] + 1 for n in previous['nodes']), default=0) if previous and previous['kind'] == 'graph' else room
            disjoint = previous and not ({n['id'] for n in previous['nodes']} & {n['id'] for n in page['nodes']})
            if previous and previous['kind'] == 'graph' and disjoint and used + extent <= room:
                previous['nodes'].extend({**n, 'y': n['y'] + used} for n in page['nodes'])
                previous['edges'].extend(page['edges'])
                continue
        packed.append(page)
    pages = packed
    node_pages, edge_pages = {}, {}
    for number, page in enumerate(pages, 1):
        for node in page['nodes']:
            node_pages.setdefault(node['id'], number)
        if 'task' in page:
            node_pages.setdefault(page['task'], number)
    # Long source IDs never collide after title clipping: @N is a stable source
    # index, and exact sanitized ID segments remain reachable in identity pages.
    for task in tasks:
        if cells(clean(task['id'])) <= 10:
            continue
        parts, part = [], ''
        for char in clean(task['id']):
            if cells(part + char) > max(1,width-1):
                parts.append(part); part = ''
            part += char
        if part: parts.append(part)
        for start in range(0,len(parts),max(1,room-1)):
            pages.append({'kind':'identity', 'nodes':[], 'edges':[], 'task':task['id'],
                          'lines':[refs[task['id']]+' ID '+str(start+1)+'/'+str(len(parts)),
                                   *parts[start:start+max(1,room-1)]]})
    # A bounded edge directory provides BOTH primary endpoint pages for every edge.
    # It is reachable with existing n/p even when a dense page footer is clipped.
    # Header + three complete rows per entry: refs/pages, source ID, target ID.
    # Two/three-row bodies split the same detail, repeating BOTH endpoint refs
    # on every piece. Never consume the caller's continuation/provenance rows.
    if room < 4:
        for edge in edges:
            edge_pages[tuple(edge)] = len(pages) + 1
            for start in range(0, 3, room - 1):
                pages.append({'kind': 'portal', 'nodes': [], 'edges': [edge],
                              'detail_start': start, 'detail_count': room - 1})
    else:
        per_page = max(1, (room - 1) // 3)
        for start in range(0, len(edges), per_page):
            selected = edges[start:start+per_page]
            for edge in selected:
                edge_pages[tuple(edge)] = len(pages) + 1
            pages.append({'kind': 'portal', 'nodes': [], 'edges': selected})
    return {'pages': pages or [{'kind': 'text', 'lines': ['작업 없음' + (' | 조직 미기록' if not snapshot.get('organization') else '')], 'nodes': [], 'edges': []}],
            'refs': refs, 'node_pages': node_pages, 'edge_pages': edge_pages, 'edges': edges,
            'unit': unit, 'room': room, 'node_width': node_width}


def lane(snapshot, task, ascii=False):
    teams = (snapshot.get('organization') or {}).get('teams', [])
    team = next((t for t in teams if t['id'] == task.get('team_id')), None)
    if team is None:
        return 'Team unknown | no org record' if ascii else '소속 미확인 | 조직 미기록'
    return '[' + safe(team['id'], ascii) + '] ' + safe(team['label'], ascii)


def _put(canvas, x, y, text):
    """Canvas cells use empty continuation slots for wide glyphs."""
    for c in text:
        size = cells(c)
        if size == 0:
            if x > 0:
                at = x-1
                while at > 0 and canvas[y][at] == '':
                    at -= 1
                canvas[y][at] += c
            continue
        if 0 <= y < len(canvas) and 0 <= x and x + size <= len(canvas[y]):
            canvas[y][x] = c
            for offset in range(1, size):
                canvas[y][x+offset] = ''
        x += size


def draw_page(snapshot, plan, index, width, ascii=False):
    page = plan['pages'][index]
    by_id = {t['id']: t for t in snapshot['tasks']}
    refs, node_pages = plan['refs'], plan['node_pages']
    if page['kind'] in ('text', 'identity'):
        if not snapshot['tasks']:
            return ['No tasks | Organization unknown'] if ascii else page['lines']
        if ascii and page['kind'] == 'text' and 'task' in page:
            identity = page['task']; task = by_id[identity]
            fields = [refs[identity]+' ID: '+safe(identity,True), safe(task.get('title') or 'Title unknown',True),
                      *state_class(task,True), model_label(task,True), specialist_label(task,True)]
            return fields[page['start']:page['start']+page['count']]
        return [safe(line, ascii) for line in page['lines']]
    if page['kind'] == 'portal':
        lines = ['Prerequisite / not execution' if ascii else '선행 연결 · 실행 순서 관측 아님']
        for source, target in page['edges']:
            lines.extend([refs[source] + ' [' + str(node_pages[source]) + '] ' + ('->' if ascii else '→') +
                          ' ' + refs[target] + ' [' + str(node_pages[target]) + ']',
                          'ID: ' + safe(source, ascii), ' -> ' + safe(target, ascii)])
        if 'detail_start' in page:
            # One edge, same original header/IDs, with page-addressed identity
            # repeated on each reachable piece instead of clipping any rows.
            details = [lines[0], *lines[2:]]
            start = page['detail_start']
            return [lines[1], *details[start:start+page['detail_count']]]
        return lines
    bottom = max(n['y'] + n['height'] + 1 for n in page['nodes'])
    canvas = [[' '] * width for _ in range(bottom)]
    for n in page['nodes']:
        x, y, w = n['x'], n['y'], n['width']
        task = by_id[n['id']]
        _put(canvas, x, y, pad(lane(snapshot, task, ascii), w))
        _put(canvas, x, y+1, ('+' if ascii else '╭') + ('-' if ascii else '─') * (w-2) + ('+' if ascii else '╮'))
        fields = task_fields(task, refs[n['id']], w-4, page['split'], ascii)
        # ASCII state can be longer, but never becomes Korean question marks.
        for j, field in enumerate(fields):
            _put(canvas, x, y+2+j, ('| ' if ascii else '│ ') + pad(field, w-4) + (' |' if ascii else ' │'))
        _put(canvas, x, y+n['height'], ('+' if ascii else '╰') + ('-' if ascii else '─') * (w-2) + ('+' if ascii else '╯'))
    nodes = {n['id']: n for n in page['nodes']}
    paths = {}
    tips = []
    # At most a pair or a star: junctions are joins, never unlabeled crossings.
    for source, target in page['edges']:
        a, b = nodes[source], nodes[target]
        x0, x1 = a['x'] + a['width'] - 1, b['x']
        y0, y1 = a['y'] + 4, b['y'] + 4
        mid = x0 + 2
        points = [(x, y0) for x in range(x0, mid+1)]
        step = 1 if y1 >= y0 else -1
        points += [(mid, y) for y in range(y0+step, y1+step, step)]
        points += [(x, y1) for x in range(mid+1, x1+1)]
        for (x,y), (xx,yy) in zip(points, points[1:]):
            direction = 'E' if xx > x else 'S' if yy > y else 'N'
            opposite = {'E':'W', 'S':'N', 'N':'S'}[direction]
            paths.setdefault((x,y), set()).add(direction)
            paths.setdefault((xx,yy), set()).add(opposite)
        tips.append((x1-1, y1))
    glyphs = {'EW':'─', 'NS':'│', 'ES':'╭', 'SW':'╮', 'EN':'╰', 'NW':'╯',
              'ENS':'├', 'NSW':'┤', 'ESW':'┬', 'ENW':'┴', 'ENSW':'┼'}
    for (x,y), directions in paths.items():
        key = ''.join(sorted(directions))
        char = ('+' if len(directions)>2 else '|' if directions <= set('NS') else '-') if ascii else glyphs.get(key, '─')
        _put(canvas, x, y, char)
    for x,y in tips:
        _put(canvas, x, y, '>' if ascii else '▶')
    # Preserve node border junctions at both actual endpoints.
    for source, target in page['edges']:
        a, b = nodes[source], nodes[target]
        _put(canvas, a['x']+a['width']-1, a['y']+4, '+' if ascii else '├')
        _put(canvas, b['x'], b['y']+4, '+' if ascii else '┤')
    return [''.join(row).rstrip() for row in canvas]


def page_spans(snapshot, plan, index):
    """(row, cell-start, cell-end, SGR) from actual node/field metadata.

    Geometry is plain-text only. The caller clips first, then applies these spans
    without changing a single displayed character, including combining glyphs.
    """
    page = plan['pages'][index]
    by_id = {t['id']: t for t in snapshot['tasks']}
    spans = []
    for node in page['nodes']:
        task = by_id[node['id']]
        x, y, inner = node['x'] + 2, node['y'] + 2, node['width'] - 4
        title = task_fields(task, plan['refs'][node['id']], inner, page['split'])[0]
        spans.append((y, x, x + cells(fit(title, inner)), '1;39'))
        state = state_class(task)[0]
        spans.append((y + 1, x, x + min(inner, cells(state)), STATE_STYLES.get(task.get('state'), '39')))
    if page['kind'] == 'text' and 'task' in page:
        task = by_id[page['task']]
        for position, style in [(1, '1;39'), (2, STATE_STYLES.get(task.get('state'), '39'))]:
            row = position - page['start']
            if 0 <= row < len(page['lines']):
                spans.append((row, 0, cells(page['lines'][row]), style))
    return spans


def continuation(plan, index, ascii=False):
    page = plan['pages'][index]
    refs, locations, edges = plan['refs'], plan['node_pages'], plan['edges']
    arrow = '->' if ascii else '→'
    visible = {n['id'] for n in page['nodes']}
    hidden = [(a,b) for a,b in edges if (a in visible or b in visible) and (a,b) not in page['edges']]
    if page['kind'] == 'portal':
        hidden = list(page['edges'])
    if hidden:
        a,b = hidden[0]
        return (refs[a] + '[' + str(locations[a]) + '] ' + arrow + ' ' + refs[b] + '[' +
                str(locations[b]) + '] | ' + ('edges: ' if ascii else '전체 연결: ') +
                str(min(plan['edge_pages'].values())) + '-' + str(max(plan['edge_pages'].values())) + ' (n/p)')
    if page['edges']:
        return ('Prerequisite arrows; not live execution' if ascii else '화살표 = 선행 조건 · 실행/동시 진행 관측 아님')
    return 'No declared edges; independence unknown' if ascii else '표시된 선행 없음 · 독립 여부 미확인'
