"""Pure keyboard navigation over checked snapshots; no record or terminal I/O."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
import status_tui_graph as graph
import status_tui_wide as wide


@dataclass
class State:
    screen: str = 'map'
    layout: str = 'wide'
    scope: str = 'all'
    value: str = ''
    selected: str = ''
    index: int = 0
    page: int = 0
    history: list = field(default_factory=list)


def regions(snapshot):
    """Three recorded Kahn layers per region, not time or observed concurrency."""
    tasks = snapshot['tasks']
    remaining = {task['id'] for task in tasks}
    done, layers = set(), []
    while remaining:
        layer = [task['id'] for task in tasks if task['id'] in remaining and set(task.get('needs', [])) <= done]
        if not layer: layer = [task['id'] for task in tasks if task['id'] in remaining]
        layers.append(layer)
        done.update(layer)
        remaining.difference_update(layer)
    return [sum(layers[i:i + 3], []) for i in range(0, len(layers), 3)]


def scope_ids(snapshot, state):
    tasks = snapshot['tasks']
    if state.scope == 'team':
        ids = [task['id'] for task in tasks if (task.get('team_id') or '') == state.value]
    elif state.scope == 'region':
        groups = regions(snapshot)
        index = int(state.value) if state.value.isdigit() else -1
        ids = groups[index] if 0 <= index < len(groups) else []
    else:
        ids = [task['id'] for task in tasks]
    if state.layout == 'focus':
        edges = graph.known_edges(snapshot)
        adjacent = {end for edge in edges if state.selected in edge for end in edge} | {state.selected}
        return [tid for tid in ids if tid in adjacent]
    return ids


def reconcile(snapshot, state):
    """Keep exact selection, scope and page through state-only refresh/resize."""
    result = copy.deepcopy(state)
    tasks = snapshot['tasks']
    identities = {task['id'] for task in tasks}
    if result.selected not in identities:
        result.selected = tasks[0]['id'] if tasks else ''
        result.index = result.page = 0
    if result.scope == 'team' and result.value not in {task.get('team_id') or '' for task in tasks}:
        result.scope, result.value = 'all', ''
    if result.scope == 'region' and (not result.value.isdigit() or int(result.value) >= len(regions(snapshot))):
        result.scope, result.value = 'all', ''
    return result


def teams(snapshot):
    result = [(team['id'], team['label']) for team in (snapshot.get('organization') or {}).get('teams', [])]
    if any(not task.get('team_id') for task in snapshot['tasks']): result.append(('', '소속 미확인'))
    return result


def links(snapshot, state):
    return [edge for edge in graph.known_edges(snapshot) if state.selected in edge]


def _push(state):
    state.history.append({key: copy.deepcopy(value) for key, value in vars(state).items() if key != 'history'})
    state.index = state.page = 0


def transition(snapshot, state, key):
    result = reconcile(snapshot, state)
    if key == 'b':
        if result.history:
            for name, value in result.history.pop().items(): setattr(result, name, value)
        return reconcile(snapshot, result)
    if key in ('v', 't', 'r', 'l', 's'):
        if key in ('l', 's') and not result.selected: return result
        _push(result)
        result.screen = {'v': 'overview', 't': 'teams', 'r': 'regions', 'l': 'links', 's': 'source'}[key]
        return result
    if key in ('w', 'x'):
        _push(result)
        result.screen, result.layout = 'map', 'wide' if key == 'w' else 'focus'
        return result
    if key in ('n', 'p'):
        result.page += 1 if key == 'n' else -1
        return result
    if result.screen == 'map':
        # In focus, j/k still reaches every task in the declared team/region.
        broad = copy.deepcopy(result)
        broad.layout = 'wide'
        ids = scope_ids(snapshot, broad)
        if key in ('j', 'k') and ids:
            current = ids.index(result.selected) if result.selected in ids else 0
            result.selected = ids[(current + (1 if key == 'j' else -1)) % len(ids)]
            result.page = 0
        elif key == 'enter' and result.selected:
            _push(result)
            result.layout = 'focus'
    else:
        entries = teams(snapshot) if result.screen == 'teams' else links(snapshot, result) if result.screen == 'links' else regions(snapshot)
        if result.screen == 'source': return result
        if key in ('j', 'k') and entries:
            result.index = (result.index + (1 if key == 'j' else -1)) % len(entries)
            result.page = 0
        if key == 'enter' and entries:
            index = result.index % len(entries)
            choice = entries[index]
            previous = result.selected
            _push(result)
            result.screen = 'map'
            result.layout = 'wide'
            if state.screen == 'teams':
                result.scope, result.value = 'team', choice[0]
            elif state.screen == 'links':
                result.scope, result.value, result.layout = 'all', '', 'focus'
                result.selected = choice[1] if choice[0] == previous else choice[0]
            else:
                result.scope, result.value = 'region', str(index)
            ids = scope_ids(snapshot, result)
            if result.selected not in ids: result.selected = ids[0] if ids else ''
    return result


def source_rows(snapshot, selected, width, ascii=False):
    task = next((task for task in snapshot['tasks'] if task['id'] == selected), None)
    value = {'task': task, 'binding': snapshot.get('binding'), 'sources': snapshot.get('sources'),
             'input_pins': snapshot.get('input_pins'), 'context_provenance': snapshot.get('context_provenance'),
             'record_observation': snapshot.get('record_observation'),
             'overall_goal_acceptance': snapshot.get('overall_goal_acceptance')}
    if 'orca_observation' in snapshot:
        value['orca_observation'] = snapshot['orca_observation']
    return [part for line in json.dumps(value, ensure_ascii=ascii, indent=2).splitlines()
            for part in wide.wrap(graph.safe(line, ascii), width)]


def text_pages(rows, room):
    return [rows[i:i + room] for i in range(0, len(rows), room)] or [[]]


def summary(snapshot):
    """Recorded three-layer groups and counted boundary edges, never a team DAG."""
    groups = regions(snapshot)
    by_id = {task['id']: task for task in snapshot['tasks']}
    owner = {tid: i for i, members in enumerate(groups) for tid in members}
    edges = graph.known_edges(snapshot)
    aggregates = {}
    for edge in edges:
        a, b = map(owner.__getitem__, edge)
        if a != b: aggregates.setdefault((a, b), []).append(edge)
    cards = [{'region': i, 'task_ids': members, 'label_source': members[0],
              'label': by_id[members[0]].get('title') or '?',
              'internal_count': sum(a in members and b in members for a, b in edges)}
             for i, members in enumerate(groups)]
    links = [{'from_region': a, 'to_region': b, 'count': len(exact), 'exact_edges': exact}
             for (a, b), exact in sorted(aggregates.items())]
    return cards, links


def summary_rows(card, width, ascii=False):
    label = card['label']
    if label == '?': label = 'Title unknown' if ascii else '제목 미확인'
    return [f"Region {card['region'] + 1} / work group" if ascii else f"구간 {card['region'] + 1} · 작업묶음",
            *wide.wrap(graph.safe(label, ascii), width),
            f"Inside {len(card['task_ids'])} tasks omitted" if ascii else f"내부 {len(card['task_ids'])}작업 생략",
            f"Internal edges {card['internal_count']}" if ascii else f"내부 의존 {card['internal_count']}개"]


def summary_plan(snapshot, state, width, room, ascii=False):
    cards, aggregates = summary(snapshot)
    # Preserve all title cells. An oversize summary uses the text continuation
    # path below instead of clipping its label or dropping aggregate counts.
    boxwidth = min(76, width - 4)
    rows = [summary_rows(card, boxwidth - 4, ascii) for card in cards]
    if not cards or width < 34 or any(len(lines) + 2 > room for lines in rows): return None
    pages, boxes, y = [], {}, 0
    for card, lines in zip(cards, rows):
        height = len(lines) + 2
        if y + height > room:
            pages.append({'boxes': boxes})
            boxes, y = {}, 0
        boxes[card['region']] = (2, y, boxwidth, height)
        y += height + 2
    if boxes: pages.append({'boxes': boxes})
    for page in pages:
        boxes = page['boxes']
        page['aggregates'] = [edge for edge in aggregates
                              if edge['from_region'] in boxes and edge['to_region'] in boxes
                              and boxes[edge['to_region']][1] == boxes[edge['from_region']][1] + boxes[edge['from_region']][3] + 2
                              and graph.cells(f"Boundary {edge['count']} aggregate" if ascii else f"경계 {edge['count']}개 집계") <= width - 7]
    return {'kind': 'summary', 'pages': pages, 'cards': cards, 'aggregates': aggregates,
            'room': room, 'state': state}


def draw_summary(view, index, width, ascii=False):
    canvas = wide.Canvas(width, view['room'])
    boxes = view['pages'][index]['boxes']
    # Only neighboring boxes have an unambiguous two-row counted arrow here.
    # Skip/boundary links remain explicitly undrawn, with original identities.
    for aggregate in view['pages'][index]['aggregates']:
        x, y, w, h = boxes[aggregate['from_region']]
        label = f"Boundary {aggregate['count']} aggregate" if ascii else f"경계 {aggregate['count']}개 집계"
        canvas.put(x + 2, y + h, '|' if ascii else '│', 'accent')
        canvas.put(x + 2, y + h + 1, 'v' if ascii else '▼', 'accent')
        canvas.put(x + 5, y + h, label, 'accent')
    selected = view['state'].index % len(view['cards'])
    co = ('+', '+', '+', '+') if ascii else ('╭', '╮', '╰', '╯')
    hz, vt = ('-', '|') if ascii else ('─', '│')
    for card in view['cards']:
        if card['region'] not in boxes: continue
        x, y, w, h = boxes[card['region']]
        role = 'focus' if card['region'] == selected else 'border'
        canvas.put(x, y, co[0] + hz * (w - 2) + co[1], role)
        canvas.put(x, y + h - 1, co[2] + hz * (w - 2) + co[3], role)
        if card['region'] == selected: canvas.put(x, y, '>' if ascii else '◆', role)
        for j, line in enumerate(summary_rows(card, w - 4, ascii)):
            canvas.put(x, y + 1 + j, vt, role)
            canvas.put(x + w - 1, y + 1 + j, vt, role)
            canvas.put(x + 2, y + 1 + j, line, 'title' if j == 1 else 'secondary')
    return canvas, []


def plan(snapshot, state, width, room, ascii=False):
    state = reconcile(snapshot, state)
    ids = scope_ids(snapshot, state)
    by_id = {task['id']: task for task in snapshot['tasks']}
    if state.screen == 'map' and ids and width >= 22 and room >= 5:
        packed = wide.layout(snapshot, width, room, ids, ascii)
        return {'kind': 'map', **packed, 'state': state}
    if state.screen in ('overview', 'regions'):
        packed = summary_plan(snapshot, state, width, room, ascii)
        if packed is not None: return packed
    rows = []
    if state.screen == 'map':
        for tid in ids:
            task = by_id[tid]
            title = task.get('title')
            if title in (None, '', '?'): title = 'Title unknown' if ascii else '제목 미확인'
            title = graph.safe(title, ascii)
            values = ['ID: ' + graph.safe(tid, ascii) + ' ', title]
            if graph.standalone_run_task(task):
                values.extend((graph.state_class(task, ascii)[0], *graph.launch_model_labels(task, ascii)))
            else:
                values.extend((*graph.state_class(task, ascii),
                               graph.model_label(task, ascii), graph.specialist_label(task, ascii)))
            rows.extend(part for value in values for part in wide.wrap(value, width))
    elif state.screen == 'source':
        rows = source_rows(snapshot, state.selected, width, ascii)
    elif state.screen == 'links':
        entries = links(snapshot, state)
        if entries:
            source, target = entries[state.index % len(entries)]
            values = [('Exact recorded prerequisite ' if ascii else '원본 단일 선행 연결 ') + str(state.index % len(entries) + 1) + '/' + str(len(entries)),
                      ('Source: ' if ascii else '시작: ') + by_id[source]['title'],
                      'ID: ' + source, ' -> ' + by_id[target]['title'], 'ID: ' + target,
                      'Enter: other endpoint' if ascii else 'Enter: 반대편 작업 · s: 선택 작업 원문']
            rows = [part for value in values for part in wide.wrap(graph.safe(value, ascii), width)]
        else:
            rows = ['No recorded links; Enter disabled' if ascii else '기록된 연결 없음 · Enter 비활성']
    elif state.screen == 'teams':
        entries = teams(snapshot)
        if entries:
            index = state.index % len(entries)
            tid, label = entries[index]
            count = sum((task.get('team_id') or '') == tid for task in snapshot['tasks'])
            values = [f'> {index + 1}/{len(entries)} ' + label, 'ID: ' + tid,
                      str(count) + (' tasks; org is not task DAG' if ascii else ' 작업 · 조직은 작업 의존과 별개'),
                      'Registry is not staffing' if ascii else '선언 조직 · 실제 배치 관측 없음']
            rows = [part for value in values for part in wide.wrap(graph.safe(value, ascii), width)]
        else:
            rows = ['Organization unknown; Enter disabled' if ascii else '조직 정보 없음 · Enter 비활성']
    else:
        cards, aggregates = summary(snapshot)
        if cards:
            card = cards[state.index % len(cards)]
            values = ['Recorded 3-layer groups; not execution order' if ascii else '기록 위상 3층씩 묶음 · 실행 순서 아님',
                      *summary_rows(card, width, ascii)]
            for edge in aggregates:
                if card['region'] in (edge['from_region'], edge['to_region']):
                    values.append((f"Region {edge['from_region'] + 1} -> {edge['to_region'] + 1}: {edge['count']} boundary edges (aggregate)" if ascii else
                                   f"구간 {edge['from_region'] + 1} → {edge['to_region'] + 1}: 경계 {edge['count']}개 집계"))
            values.append('Enter map; l exact links' if ascii else 'Enter 지도 · l 원본 단일 연결')
            rows = [part for value in values for part in wide.wrap(graph.safe(value, ascii), width)]
        else:
            rows = ['No tasks; Enter disabled' if ascii else '작업 없음 · Enter 비활성']
    if not rows: rows = ['No tasks | Organization unknown' if ascii else '작업 없음 · 조직 미기록' if not snapshot.get('organization') else '작업 없음']
    return {'kind': 'text', 'pages': text_pages(rows, max(1, room)), 'state': state, 'room': room}


def page_index(view, requested=None):
    state = view['state']
    base = 0
    if view['kind'] == 'map':
        base = next((i for i, page in enumerate(view['pages']) if state.selected in page['boxes']), 0)
    elif view['kind'] == 'summary':
        selected = state.index % len(view['cards'])
        base = next(i for i, page in enumerate(view['pages']) if selected in page['boxes'])
    return (base + (state.page if requested is None else requested)) % len(view['pages'])


def draw(snapshot, view, index, width, ascii=False):
    if view['kind'] == 'map':
        return wide.draw(snapshot, view, index, width, view['state'].selected, ascii)
    if view['kind'] == 'summary':
        return draw_summary(view, index, width, ascii)
    canvas = wide.Canvas(width, view['room'])
    for row, line in enumerate(view['pages'][index]): canvas.put(0, row, line)
    return canvas, []
