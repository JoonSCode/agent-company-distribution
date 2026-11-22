"""Default wide product contracts, independent of the retained legacy geometry."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import signal
import tempfile
import termios
import unittest
from unittest.mock import patch

import status_tui as tui
import status_tui_graph as graph
import status_tui_navigation as nav
import status_tui_wide as wide
from test_status_tui import OwnedPTY
from test_status_tui_context import enriched
from test_status_tui_data import fixture, dump


def cell_slice(line, x, count):
    output, used = '', 0
    for char in line:
        size = graph.cells(char)
        if x <= used < x + count: output += char
        used += size
    return output


def reconstruct(frame, node, offset=2):
    lines = frame.splitlines()
    return {key: ''.join(cell_slice(lines[y + offset], x, count) for x, y, count in spans)
            for key, spans in node['field_spans'].items()}


def styled_cells(line):
    result, position, style, start = {}, 0, None, 0
    for match in re.finditer(r'\x1b\[([0-9;]*)m', line):
        for char in line[start:match.start()]:
            size = graph.cells(char)
            for offset in range(size): result[position + offset] = style
            position += size
        style = None if match[1] in ('', '0') else match[1]
        start = match.end()
    for char in line[start:]:
        size = graph.cells(char)
        for offset in range(size): result[position + offset] = style
        position += size
    return result


class WideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        fixture(self.root, count=40)
        self.snapshot = tui.load_snapshot(self.root / 'view.json')
        for task in self.snapshot['tasks']:
            task.update(assigned_model='gpt-5.1', model_basis='assigned',
                        specialist={'status': 'assigned', 'id': 'agent-company-development'})

    def test_connected_summary_cards_exact_aggregates_and_all_regions(self):
        snap = copy.deepcopy(self.snapshot)
        # Include a nonadjacent region link; never invent all-to-all links.
        snap['tasks'][7]['needs'].append('t1')
        frozen = copy.deepcopy(snap)
        groups = nav.regions(snap)
        edges = graph.known_edges(snap)
        owner = {tid: i for i, members in enumerate(groups) for tid in members}
        expected = {}
        for edge in edges:
            a, b = map(owner.__getitem__, edge)
            if a != b: expected.setdefault((a, b), []).append(edge)
        for screen in ('overview', 'regions'):
            reached = set()
            state = nav.State(selected='t1', screen=screen)
            for i in range(len(groups)):
                self.assertEqual(state.index, i)
                frame, meta = tui.render_details(snap, 98, 27, state=state)
                self.assertEqual(meta['kind'], 'summary')
                self.assertIn('작업묶음', frame)
                self.assertIn('작업 생략', frame)
                selected = next(item for item in meta['summary_regions'] if item['region'] == i)
                self.assertEqual(selected['task_ids'], groups[i])
                self.assertEqual(selected['label_source'], groups[i][0])
                self.assertEqual(selected['label'], frozen['tasks'][int(groups[i][0][1:]) - 1]['title'])
                for item in meta['summary_regions']:
                    self.assertEqual(item['internal_count'], sum(a in item['task_ids'] and b in item['task_ids'] for a, b in edges))
                    self.assertIn(f"내부 {len(item['task_ids'])}작업 생략", frame)
                actual = {(item['from_region'], item['to_region']): item['exact_edges']
                          for item in meta['aggregate_edges'] + meta['undrawn_aggregate_edges']}
                self.assertEqual(actual, expected)
                for item in meta['aggregate_edges']:
                    self.assertEqual(item['count'], len(expected[item['from_region'], item['to_region']]))
                    self.assertIn(f"경계 {item['count']}개 집계", frame)
                entered = nav.transition(snap, state, 'enter')
                self.assertEqual(nav.scope_ids(snap, entered), groups[i])
                self.assertEqual(nav.transition(snap, entered, 'b'), state)
                reached.update(nav.scope_ids(snap, entered))
                state = nav.transition(snap, state, 'j')
            self.assertEqual(reached, {task['id'] for task in snap['tasks']})
        self.assertEqual(snap, frozen)

    def test_short_narrow_actual_cells_quit_and_all_provenance(self):
        for synthetic in (False, True):
            for coverage in ('partial', 'unknown'):
                snap = copy.deepcopy(self.snapshot)
                snap.update(input_label='synthetic' if synthetic else 'record', record_label='synthetic' if synthetic else 'record',
                            dependency_coverage=coverage)
                for width in (12, 21, 22, 48, 98):
                    for height in (7, 8, 9):
                        for screen in ('map', 'overview', 'regions', 'links', 'source', 'teams', 'org'):
                            for ascii in (False, True):
                                state = nav.State(screen='map' if screen == 'org' else screen, selected='t1')
                                with self.subTest(synthetic=synthetic, coverage=coverage, width=width, height=height, screen=screen, ascii=ascii):
                                    frame = tui.render_frame(snap, width, height, 'org' if screen == 'org' else 'combined', state=state, ascii=ascii)
                                    self.assertRegex(frame, r'\bq\b')
                                    for line in frame.splitlines(): self.assertLessEqual(graph.cells(line), width - 1)
                                    self.assertLessEqual(len(frame.splitlines()), height - 1)
                                    self.assertNotIn('\x1b', frame)
                                    full = ((('SYNTHETIC DEMO' if synthetic else 'Recorded claims') + ' | ' +
                                             ('Partial links' if coverage == 'partial' else 'Links unknown') + ' | No live observation') if ascii else
                                            (('합성 시연' if synthetic else '기록된 주장') + ' | ' +
                                             ('연결 일부만 기록' if coverage == 'partial' else '연결 정보 미확인') + ' | 실행 관측 없음'))
                                    if full not in frame:
                                        for token in (('SYNTHETIC' if synthetic else 'RECORDED', 'PART LINKS' if coverage == 'partial' else 'LINKS ?', 'NO LIVE') if ascii else
                                                      ('합성 시연' if synthetic else '기록 주장', '연결 일부' if coverage == 'partial' else '연결 불명', '관측 없음')):
                                            self.assertIn(token, frame)

    def test_normal_record_short_quit_regression_cli(self):
        import subprocess
        import sys
        from test_status_tui import child_env
        enriched(self.root)
        tui.capture_context(self.root / 'record.json', self.root / 'view.json', self.root / 'context.json')
        for ascii in (False, True):
            result = subprocess.run([sys.executable, '-B', str(Path(tui.__file__)), '--record', str(self.root / 'record.json'),
                                     '--context', str(self.root / 'context.json'), '--once', '--width', '22', '--height', '7',
                                     '--no-color', *(['--ascii'] if ascii else [])], env=child_env(self.root), capture_output=True, check=True)
            self.assertRegex(result.stdout.decode().splitlines()[-1], r'\bq\b')

    def test_narrow_continuations_and_summary_cjk_controls_empty(self):
        snap = copy.deepcopy(self.snapshot)
        snap['tasks'] = snap['tasks'][:2]
        snap['tasks'][0]['title'] = '원문 한글\u0301中文\x1b\u202e' * 8
        for width in (12, 21, 22, 48):
            for height in (7, 8, 9):
                for screen in ('map', 'source', 'links', 'overview', 'regions'):
                    state = nav.State(selected='t1', screen=screen)
                    view = tui._view(snap, width, height, 'wide', state, False)
                    rows = []
                    for i in range(len(view['pages'])):
                        state.page = i
                        frame, meta = tui.render_details(snap, width, height, state=state)
                        rows.extend(frame.splitlines()[meta['body_offset']:meta['body_offset'] + meta['body_rows']])
                        self.assertNotIn('\x1b', frame)
                        self.assertNotIn('\u202e', frame)
                        self.assertRegex(frame, r'\bq\b')
                    self.assertTrue(rows)
                    if screen == 'source':
                        self.assertEqual(''.join(rows), ''.join(line.rstrip() for line in nav.source_rows(snap, 't1', width - 1)))
        original = copy.deepcopy(snap)
        for ascii in (False, True):
            snap = copy.deepcopy(original)
            state = nav.State(selected='t1', screen='overview')
            frame, meta = tui.render_details(snap, 98, 27, state=state, ascii=ascii)
            self.assertEqual(meta['kind'], 'summary')
            self.assertNotIn('\x1b', frame)
            self.assertNotIn('\u202e', frame)
            self.assertIn('Inside 2 tasks omitted' if ascii else '내부 2작업 생략', frame)
            for i in (1, 2):
                snap['tasks'] = snap['tasks'][:1] if i == 1 else []
                frame, meta = tui.render_details(snap, 98, 27, state=state, ascii=ascii)
                if not snap['tasks']:
                    self.assertNotIn('summary_regions', meta)
                    self.assertIn('No tasks' if ascii else '작업 없음', frame)

    def test_default_density_from_actual_emitted_fields(self):
        for count, size, minimum in [(8, (98, 27), 8), (40, (98, 27), 9), (40, (120, 40), 16)]:
            snap = copy.deepcopy(self.snapshot)
            snap['tasks'] = snap['tasks'][:count]
            frame, meta = tui.render_details(snap, *size)
            full = [node for node in meta['nodes'] if reconstruct(frame, node) == node['expected_fields']]
            self.assertGreaterEqual(len(full), minimum, (size, meta))
            self.assertEqual(len(full), len(meta['nodes']))
            self.assertIn('전체 목표: 확인 대기', frame)
            self.assertIn('사용자 확인: 미관측', frame)
            self.assertIn('합성 시연', frame)

    def test_routes_have_unique_empty_cells_exact_endpoints_and_no_bus(self):
        snap = self.snapshot
        plan = wide.layout(snap, 97, 22)
        for page in plan['pages']:
            occupied = {(x, y) for xx, yy, w, h in page['boxes'].values()
                        for x in range(xx, xx + w) for y in range(yy, yy + h)}
            used, ports = set(), set()
            for route in page['routes']:
                self.assertIn(route['edge'], graph.known_edges(snap))
                self.assertFalse(set(route['path']) & occupied)
                self.assertFalse(set(route['path']) & used)
                self.assertFalse({route['source_port'], route['target_port']} & ports)
                for a, b in zip([route['source_port'], *route['path']], [*route['path'], route['target_port']]):
                    self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)
                used.update(route['path'])
                ports.update((route['source_port'], route['target_port']))
        _, meta = tui.render_details(snap, 98, 27)
        self.assertEqual(set(meta['exact_visible_edges']) | set(meta['undrawn_edges']), set(graph.known_edges(snap)))
        for edge in meta['undrawn_edges']:
            state = nav.State(selected=edge[0], screen='links')
            self.assertIn(edge, nav.links(snap, state))

    def test_all_sizes_thresholds_and_source_long_identifiers_reachable(self):
        snap = copy.deepcopy(self.snapshot)
        snap['tasks'] = snap['tasks'][:2]
        ids = ['shared-' + 'long-prefix-' * 12 + suffix for suffix in ('a', 'b')]
        for task, tid in zip(snap['tasks'], ids):
            task.update(id=tid, needs=[], title='한글\u0301中文界' * 20)
        snap['tasks'][1]['needs'] = [ids[0]]
        for width in (1, 8, 20, 48, 80, 98, 120):
            for height in (1, 4, 6, 7, 8, 9, 12, 24, 27, 40):
                for mode in tui.MODES:
                    for page in range(tui.page_count(snap, width, height, mode)):
                        frame = tui.render_frame(snap, width, height, mode, page)
                        self.assertLessEqual(len(frame.splitlines()), max(1, height - 1))
                        for line in frame.splitlines(): self.assertLessEqual(graph.cells(line), max(1, width - 1))
                        if width >= 80 and height >= 7:
                            self.assertIn('합성 시연', frame)
                            self.assertIn('연결 일부만 기록', frame)
                            self.assertIn('실행 관측 없음', frame)
                        if height < 7 or width < 12:
                            self.assertIn('q', frame.splitlines()[0])
                            self.assertNotIn('n/p', frame)
        for tid in ids:
            state = nav.State(selected=tid, screen='source')
            for height in (7, 8, 9, 27):
                view = tui._view(snap, 98, height, 'wide', state, False)
                emitted = []
                for number in range(len(view['pages'])):
                    current = copy.deepcopy(state)
                    current.page = number
                    frame = tui.render_frame(snap, 98, height, state=current)
                    emitted.extend(frame.splitlines()[2:2 + view['room']])
                self.assertIn(tid, ''.join(emitted))
                self.assertTrue(all(len(page) <= height - 5 for page in view['pages']))
        for source, target in graph.known_edges(snap):
            state = nav.State(selected=source, screen='links')
            view = tui._view(snap, 98, 7, 'wide', state, False)
            emitted = []
            for number in range(len(view['pages'])):
                current = copy.deepcopy(state)
                current.page = number
                frame = tui.render_frame(snap, 98, 7, state=current)
                emitted.extend(frame.splitlines()[2:2 + view['room']])
            raw = ''.join(emitted)
            self.assertIn(source, raw)
            self.assertIn(target, raw)

    def test_status_only_refresh_selection_paging_and_resize_stable(self):
        state = nav.State(selected='t17', page=1)
        before = wide.layout(self.snapshot, 97, 22)
        geometry = [page['boxes'] for page in before['pages']]
        for status in graph.STATES:
            changed = copy.deepcopy(self.snapshot)
            for task in changed['tasks']: task['state'] = status
            self.assertEqual(geometry, [page['boxes'] for page in wide.layout(changed, 97, 22)['pages']])
            self.assertEqual(state, nav.reconcile(changed, state))
            for size in ((98, 27), (120, 40), (48, 12)):
                _, meta = tui.render_details(changed, *size, state=state)
                self.assertEqual(meta['state']['selected'], 't17')
                self.assertEqual(meta['state']['page'], 1)

    def test_navigation_scopes_named_edges_back_and_unknown_org(self):
        snap = self.snapshot
        state = nav.State(selected='t1')
        for key in ('v', 'enter', 't', 'enter', 'r', 'enter', 'x', 'w', 'l', 'enter', 's'):
            state = nav.transition(snap, state, key)
            tui.render_frame(snap, 98, 27, state=state)
        self.assertEqual(state.screen, 'source')
        state = nav.transition(snap, state, 'b')
        self.assertEqual(state.screen, 'map')
        self.assertEqual(state.selected, 't2')
        snap = copy.deepcopy(snap)
        snap['organization'] = None
        for task in snap['tasks']: task['team_id'] = None
        state = nav.transition(snap, nav.State(selected='t1'), 't')
        self.assertIn('소속 미확인', tui.render_frame(snap, 98, 27, state=state))
        snap['tasks'] = []
        self.assertIn('Enter 비활성', tui.render_frame(snap, 98, 27, state=nav.State(screen='teams')))

    def test_semantic_color_cells_no_color_ascii_controls(self):
        snap = copy.deepcopy(self.snapshot)
        snap['tasks'] = snap['tasks'][:2]
        for task, status in zip(snap['tasks'], ('ACC', 'ERR')):
            task.update(state=status, title='오류 대기 분석\u0301\x1b\u202e', assigned_model='대기-오류-model')
        plain, meta = tui.render_details(snap, 98, 27)
        with patch.dict(os.environ, {}, clear=True):
            colored = tui.render_frame(snap, 98, 27, color=True)
        self.assertEqual(re.sub(r'\x1b\[[0-9;]*m', '', colored), plain)
        self.assertNotIn('\x1b', plain)
        self.assertNotIn('\u202e', plain)
        self.assertNotIn('\x1b[2m', colored)
        canvas, nodes = wide.draw(snap, wide.layout(snap, 97, 22), 0, 97)
        for node, status in zip(nodes, ('ACC', 'ERR')):
            x, y, _, _ = node['box']
            self.assertEqual(canvas.grid[y][x + 2][1], 'title')
            _, rows, _ = wide.content(next(task for task in snap['tasks'] if task['id'] == node['task']), node['box'][2])
            class_row = next(i for i, (key, _) in enumerate(rows) if key == 'class_state')
            state_x = x + 2 + graph.cells(node['expected_fields']['classification'] + ' · ')
            self.assertEqual(canvas.grid[y + class_row][state_x][1], status)
            emitted_status = styled_cells(colored.splitlines()[y + class_row + 2])
            expected_color = wide.PALETTES['light'][status][1]
            for cell in range(state_x, state_x + graph.cells(graph.STATES[status])):
                self.assertEqual(emitted_status[cell], expected_color)
            self.assertEqual(styled_cells(colored.splitlines()[y + 2])[x + 2], '1')
            model_y = next(i for i, (key, _) in enumerate(rows) if key == 'model')
            self.assertEqual(canvas.grid[y + model_y][x + 2][1], 'secondary')
            self.assertEqual(styled_cells(colored.splitlines()[y + model_y + 2])[x + 2],
                             wide.PALETTES['light']['secondary'][1])
        with patch.dict(os.environ, {'NO_COLOR': ''}):
            self.assertEqual(tui.render_frame(snap, 98, 27, color=True), plain)
        ascii_frame = tui.render_frame(snap, 98, 27, ascii=True, color=True)
        self.assertTrue(ascii_frame.isascii())
        self.assertNotIn('\x1b', ascii_frame)
        self.assertIn('Task review passed', ascii_frame)

    def test_goal_error_pending_and_recorded_pass_not_task_success(self):
        for kind, earned, label in [('pending', False, '확인 대기'), ('error', False, '오류'), ('success', True, '기록상 통과')]:
            self.snapshot['overall_goal_acceptance'].update(badge_kind=kind, earned_success=earned)
            frame = tui.render_frame(self.snapshot, 98, 27)
            self.assertIn('전체 목표: ' + label, frame)
            self.assertIn('사용자 확인: 미관측', frame)
        self.snapshot.update(_refresh_error='InputError', _last_good_age=5)
        frame = tui.render_frame(self.snapshot, 98, 27)
        self.assertTrue(frame.startswith('ERROR | last-good 5s'))
        self.assertIn('작업 1', frame)

    def test_model_specialist_truth_and_input_immutability(self):
        task = self.snapshot['tasks'][0]
        for basis, identity, label in [('planned', 'x7', '계획: x7'), ('assigned', 'x7', '할당: x7'),
                                       ('unknown', 'observed-only', '모델 미확인'),
                                       ('assigned', 'm1', '모델명 미확인 · 할당 ID:m1')]:
            task.update(model_basis=basis, assigned_model=identity)
            frozen = copy.deepcopy(self.snapshot)
            frame, meta = tui.render_details(self.snapshot, 98, 27)
            self.assertEqual(reconstruct(frame, meta['nodes'][0])['model'], label)
            self.assertEqual(self.snapshot, frozen)
        for status, label in [('none', '전문가 없음'), ('unknown', '전문가 미확인')]:
            task['specialist'] = {'status': status, 'id': None}
            frame, meta = tui.render_details(self.snapshot, 98, 27)
            self.assertEqual(reconstruct(frame, meta['nodes'][0])['expert'], label)

    def test_unknown_title_all_classes_states_and_ascii_words(self):
        snap = copy.deepcopy(self.snapshot)
        snap['tasks'] = snap['tasks'][:1]
        task = snap['tasks'][0]
        task['title'] = '?'
        for classification, label in graph.CLASSES.items():
            task['classification'] = classification
            frame, meta = tui.render_details(snap, 98, 27)
            fields = reconstruct(frame, meta['nodes'][0])
            self.assertEqual(fields['title'], '제목 미확인')
            self.assertEqual(fields['classification'], label)
        for state, label in graph.STATES.items():
            task['state'] = state
            self.assertIn(label, tui.render_frame(snap, 98, 27))
            self.assertIn(graph.EN_STATES[state], tui.render_frame(snap, 98, 27, ascii=True))

    def test_owned_default_navigation_real_keys(self):
        terminal = OwnedPTY(self.root, 98, 27)
        self.addCleanup(terminal.close)
        terminal.until('page:1/')
        for key, token in [('n', 'page:2/'), ('p', 'page:1/'), ('x', '초점 지도'), ('w', '넓은 지도'),
                           ('v', '전체 개요'), ('\r', '넓은 지도'), ('t', '팀 선택'), ('b', '넓은 지도'),
                           ('r', '구간 선택'), ('b', '넓은 지도'), ('l', '이름 있는 연결'), ('\r', '초점 지도'),
                           ('s', '원본·배정 근거'), ('b', '초점 지도'), ('o', '[org]'), ('f', '[flow]'), ('c', '[combined]')]:
            terminal.key(key)
            terminal.until(token)
        terminal.resize(48, 12)
        terminal.until('page:')
        receipt = terminal.close()
        self.assertEqual(receipt['exit'], 0)
        self.assertFalse(receipt['forced_kill'])
        self.assertTrue(receipt['cursor_shown'])

    def test_owned_exact_typed_termios_pendin_q_sigint(self):
        for pendin in ((0, 1) if hasattr(termios, 'PENDIN') else (0,)):
            for how in ('q', signal.SIGINT):
                with self.subTest(pendin=pendin, how=how):
                    terminal = OwnedPTY(self.root, 98, 27, pendin=pendin)
                    self.addCleanup(terminal.close)
                    terminal.until('page:1/')
                    self.assertEqual(terminal.before[3] & getattr(termios, 'PENDIN', 0) != 0, bool(pendin))
                    receipt = terminal.close(how)
                    self.assertEqual(receipt['exit'], 0, receipt)
                    self.assertFalse(receipt['forced_kill'], receipt)
                    self.assertFalse(receipt['timed_out'], receipt)
                    self.assertEqual(receipt['termios_before'], receipt['termios_after'], receipt)
                    self.assertTrue(receipt['exact_restored'], receipt)


if __name__ == '__main__': unittest.main()
