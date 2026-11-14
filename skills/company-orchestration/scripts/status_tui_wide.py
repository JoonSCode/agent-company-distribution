"""Pure full-field viewport packing and disjoint individual prerequisite routes.

Adapted from the approved card experiment, not its loaders or terminal lifecycle.
Only checked Company normalized snapshots enter here; no file, host or worker I/O.
"""
from __future__ import annotations

from collections import deque
import os
import status_tui_graph as graph

PALETTES = {
    'light': {'title': ('1', '1'), 'secondary': ('38;2;71;85;105', '38;5;240'),
              'border': ('38;2;100;116;139', '38;5;242'), 'accent': ('38;2;3;105;161', '38;5;25'),
              'focus': ('38;2;109;40;217', '38;5;92'), 'ACC': ('38;2;22;101;52', '38;5;22'),
              'WAIT': ('38;2;146;64;14', '38;5;94'), 'ERR': ('38;2;185;28;28', '38;5;124')},
    'dark': {'title': ('1', '1'), 'secondary': ('38;2;203;213;225', '38;5;252'),
             'border': ('38;2;100;116;139', '38;5;246'), 'accent': ('38;2;56;189;248', '38;5;81'),
             'focus': ('38;2;167;139;250', '38;5;141'), 'ACC': ('38;2;134;239;172', '38;5;120'),
             'WAIT': ('38;2;251;191;36', '38;5;221'), 'ERR': ('38;2;248;113;113', '38;5;203')},
}


def wrap(value, width):
    """Lossless sanitized display-cell segments, including boundary spaces."""
    width = max(1, width)
    result, line = [], ''
    for char in graph.clean(value):
        if graph.cells(line + char) > width:
            if line: result.append(line)
            line = ''
        # A two-cell glyph cannot fit a one-cell viewport; safe substitution.
        line += char if graph.cells(char) <= width else '?'
    return result + [line]


class Canvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.grid = [[(' ', '') for _ in range(width)] for _ in range(height)]

    def put(self, x, y, text, role='secondary'):
        if not 0 <= y < self.height: return
        for char in text:
            size = graph.cells(char)
            if size == 0:
                if x > 0:
                    at = min(x - 1, self.width - 1)
                    while at > 0 and self.grid[y][at][0] == '': at -= 1
                    old, previous = self.grid[y][at]
                    self.grid[y][at] = (old + char, previous)
                continue
            if 0 <= x and x + size <= self.width:
                self.grid[y][x] = (char, role)
                for offset in range(1, size): self.grid[y][x + offset] = ('', role)
            x += size

    def text(self, color=False, palette='light'):
        color = color and 'NO_COLOR' not in os.environ
        truecolor = os.environ.get('COLORTERM', '').lower() in ('truecolor', '24bit')
        colors, rows = PALETTES[palette], []
        for row in self.grid:
            end = len(row)
            while end and row[end - 1][0] == ' ': end -= 1
            output, previous = '', None
            for char, role in row[:end]:
                if not char: continue
                if color and role != previous:
                    output += '\x1b[0m'
                    if role in colors: output += '\x1b[' + colors[role][0 if truecolor else 1] + 'm'
                    previous = role
                output += char
            rows.append(output + ('\x1b[0m' if color else ''))
        return '\n'.join(rows)


def content(task, width, ascii=False):
    inner = max(1, width - 4)
    state, classification = graph.state_class(task, ascii)
    title = task.get('title')
    if title in (None, '', '?'): title = 'Title unknown' if ascii else '제목 미확인'
    values = {'title': graph.safe(title, ascii),
              'classification': classification, 'model': graph.model_label(task, ascii),
              'expert': graph.specialist_label(task, ascii)}
    rows = [('title', part) for part in wrap(values['title'], inner)]
    separator = ' | ' if ascii else ' · '
    # Use the longest legitimate state to select row structure, so a status-only
    # refresh cannot repack the selected task onto another page.
    states = (graph.EN_STATES if ascii else graph.STATES).values()
    combined = all(graph.cells(classification + separator + label) <= inner for label in states)
    if combined:
        rows.append(('class_state', classification + separator + state))
    else:
        rows.extend(('classification', part) for part in wrap(classification, inner))
        state_rows = max(len(wrap(label, inner)) for label in states)
        parts = wrap(state, inner)
        rows.extend(('state', parts[i] if i < len(parts) else '') for i in range(state_rows))
    for key in ('model', 'expert'):
        rows.extend((key, part) for part in wrap(values[key], inner))
    return values, rows, len(rows) + 1


def packing(tasks, width, room, ascii=False):
    """Physical capacity, not a task-count cap; preserve source order."""
    choices = []
    for columns in range(1, max(1, (width + 4) // 26) + 1):
        gap = 4
        card_width = (width - gap * (columns - 1)) // columns
        if card_width < 22: continue
        pages, boxes, y, i = [], {}, 0, 0
        while i < len(tasks):
            row = tasks[i:i + columns]
            heights = [content(task, card_width, ascii)[2] for task in row]
            extent = max(heights)
            if extent > room:
                if boxes: pages.append(boxes); boxes, y = {}, 0
                task = row[0]
                pages.append({task['id']: (0, 0, width, min(room, content(task, width, ascii)[2]))})
                i += 1
                continue
            if y + extent > room:
                pages.append(boxes); boxes, y = {}, 0
            for j, (task, height) in enumerate(zip(row, heights)):
                boxes[task['id']] = (j * (card_width + gap), y, card_width, height)
            y += extent + 2
            i += len(row)
        if boxes: pages.append(boxes)
        pages = pages or [{}]
        choices.append(((len(pages[0]), -len(pages), card_width), pages, columns))
    if not choices: return [{}], 1
    _, pages, columns = max(choices, key=lambda choice: choice[0])
    return pages, columns


def ports(box):
    x, y, width, height = box
    result = []
    for yy in range(y + 1, y + height - 1):
        result.extend([((x - 1, yy), (x, yy)), ((x + width, yy), (x + width - 1, yy))])
    for xx in range(x + 2, x + width - 2):
        result.extend([((xx, y - 1), (xx, y)), ((xx, y + height), (xx, y + height - 1))])
    return result


def exact_routes(boxes, edges, width, height):
    blocked = {(xx, yy) for x, y, w, h in boxes.values() for xx in range(x, x + w) for yy in range(y, y + h)}
    used, claimed, routes = set(), set(), []
    def distance(edge):
        a, b = boxes[edge[0]], boxes[edge[1]]
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    for source, target in sorted(edges, key=distance):
        def free(point):
            return 0 <= point[0] < width and 0 <= point[1] < height and point not in blocked and point not in used
        starts = {q: p for q, p in ports(boxes[source]) if free(q) and p not in claimed}
        ends = {q: p for q, p in ports(boxes[target]) if free(q) and p not in claimed}
        if not starts or not ends: continue
        queue, previous, found = deque(starts), {q: None for q in starts}, None
        while queue:
            point = queue.popleft()
            if point in ends:
                found = point
                break
            x, y = point
            for nxt in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
                if nxt not in previous and free(nxt):
                    previous[nxt] = point
                    queue.append(nxt)
        if found is None: continue
        path, point = [], found
        while point is not None:
            path.append(point)
            point = previous[point]
        path.reverse()
        start, end = starts[path[0]], ends[path[-1]]
        used.update(path)
        claimed.update((start, end))
        routes.append({'edge': (source, target), 'path': path, 'source_port': start, 'target_port': end})
    return routes


def paint_routes(canvas, routes, ascii=False):
    glyphs = {frozenset('LR'): '─', frozenset('UD'): '│', frozenset('RD'): '┌',
              frozenset('LD'): '┐', frozenset('RU'): '└', frozenset('LU'): '┘'}
    def direction(a, b):
        return 'R' if b[0] > a[0] else 'L' if b[0] < a[0] else 'D' if b[1] > a[1] else 'U'
    for route in routes:
        path = [route['source_port'], *route['path'], route['target_port']]
        for i in range(1, len(path) - 1):
            dirs = frozenset((direction(path[i], path[i - 1]), direction(path[i], path[i + 1])))
            glyph = ('-' if dirs == frozenset('LR') else '|' if dirs == frozenset('UD') else '+') if ascii else glyphs[dirs]
            if i == len(path) - 2:
                d = direction(path[i], path[i + 1])
                glyph = ({'R': '>', 'L': '<', 'D': 'v', 'U': '^'} if ascii else
                         {'R': '▶', 'L': '◀', 'D': '▼', 'U': '▲'})[d]
            canvas.put(*path[i], glyph, 'accent')


def draw_card(canvas, task, box, selected=False, ascii=False, team_label=''):
    x, y, width, height = box
    values, rows, needed = content(task, width, ascii)
    corners = ('+', '+', '+', '+') if ascii else ('╭', '╮', '╰', '╯')
    horizontal, vertical = ('-', '|') if ascii else ('─', '│')
    role = 'focus' if selected else 'border'
    spans = {key: [] for key in values}
    canvas.put(x, y, corners[0] + horizontal * (width - 2) + corners[1], role)
    if selected: canvas.put(x, y, '>' if ascii else '◆', role)
    for yy in range(y + 1, y + height - 1):
        canvas.put(x, yy, vertical, role)
        canvas.put(x + width - 1, yy, vertical, role)
    canvas.put(x, y + height - 1, corners[2] + horizontal * (width - 2) + corners[3], role)
    if team_label:
        canvas.put(x + 2, y + height - 1, graph.fit(graph.safe(team_label, ascii), width - 4), 'secondary')
    state_role = {'ACC': 'ACC', 'WAIT': 'WAIT', 'SUB': 'WAIT', 'ERR': 'ERR', 'FAIL': 'ERR'}.get(task.get('state'), 'secondary')
    for i, (key, text) in enumerate(rows):
        yy, xx = y + i, x + 2
        if yy >= y + height - 1: break
        if i == 0:
            canvas.put(x + 1, yy, ' ', 'title')
            canvas.put(xx + graph.cells(text), yy, ' ', 'title')
        canvas.put(xx, yy, text, 'title' if key == 'title' else state_role if key == 'state' else 'secondary')
        if key == 'class_state':
            classification = values['classification']
            spans['classification'].append((xx, yy, graph.cells(classification)))
            offset = graph.cells(classification + (' | ' if ascii else ' · '))
            canvas.put(xx + offset, yy, text[len(classification) + 3:], state_role)
        elif key in spans:
            spans[key].append((xx, yy, graph.cells(text)))
    partial = needed > height
    if partial:
        canvas.put(x + 2, y + height - 1, graph.fit('~ s source' if ascii else '~ s 원문', width - 4), 'accent')
    return {'task': task['id'], 'box': box, 'full_fields': not partial,
            'field_spans': spans, 'expected_fields': values, 'truncated': partial}


def layout(snapshot, width, room, ids=None, ascii=False):
    tasks = snapshot['tasks']
    if ids is not None:
        allowed = set(ids)
        tasks = [task for task in tasks if task['id'] in allowed]
    pages, columns = packing(tasks, width, room, ascii)
    edges = graph.known_edges(snapshot)
    result = []
    for boxes in pages:
        local = [edge for edge in edges if edge[0] in boxes and edge[1] in boxes]
        routes = exact_routes(boxes, local, width, room) if room >= 5 else []
        result.append({'boxes': boxes, 'routes': routes})
    return {'pages': result, 'columns': columns, 'edges': edges, 'room': room}


def draw(snapshot, plan, index, width, selected='', ascii=False):
    page = plan['pages'][index]
    canvas = Canvas(width, plan['room'])
    paint_routes(canvas, page['routes'], ascii)
    by_id = {task['id']: task for task in snapshot['tasks']}
    teams = {team['id']: '[' + team['id'] + '] ' + team['label']
             for team in (snapshot.get('organization') or {}).get('teams', [])}
    nodes = [draw_card(canvas, by_id[tid], box, tid == selected, ascii,
                       teams.get(by_id[tid].get('team_id'), 'Team unknown' if ascii else '소속 미확인'))
             for tid, box in page['boxes'].items()]
    return canvas, nodes
