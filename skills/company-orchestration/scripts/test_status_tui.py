#!/usr/bin/env python3
"""Actual renderer/CLI/owned PTY tests; no Orca or installed terminal mutation."""
from __future__ import annotations
import copy
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
import status_tui as tui
import status_tui_data as data
from test_status_tui_data import fixture, dump

SCRIPT = Path(__file__).with_name('status_tui.py')


def child_env(root):
    return {'PATH': '/usr/bin:/bin', 'HOME': str(root), 'CODEX_HOME': str(root / 'codex'),
            'GH_CONFIG_DIR': str(root / 'gh'), 'TMPDIR': str(root), 'TERM': 'xterm-256color',
            'LANG': 'en_US.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
            'NO_COLOR': '1'}


def semantic(attrs):
    value = copy.deepcopy(attrs)
    value[3] &= ~getattr(termios, 'PENDIN', 0)
    return value


class OwnedPTY:
    def __init__(self, root, width=80, height=12, extra=(), *, pendin=None):
        self.root = Path(root)
        self.master, self.slave = pty.openpty()
        self.resize(width, height, notify=False)
        if pendin is not None:
            attrs = termios.tcgetattr(self.slave)
            flag = getattr(termios, 'PENDIN', 0)
            attrs[3] = (attrs[3] | flag) if pendin else (attrs[3] & ~flag)
            termios.tcsetattr(self.slave, termios.TCSANOW, attrs)
        self.before = termios.tcgetattr(self.slave)
        self.raw = bytearray()
        self.stderr_raw = bytearray()
        self.stderr_eof = False
        self.started_ns = time.time_ns()
        self.proc = subprocess.Popen([sys.executable, '-B', str(SCRIPT), '--manifest', str(self.root / 'view.json'),
                                      '--interval', '0.25', *extra], stdin=self.slave, stdout=self.slave,
                                     stderr=subprocess.PIPE, env=child_env(self.root), start_new_session=True)
        self.closed = False

    def resize(self, width, height, notify=True):
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
        if notify: self.proc.send_signal(signal.SIGWINCH)

    def collect(self, seconds=0.1):
        deadline = time.monotonic() + seconds
        chunk = bytearray()
        while time.monotonic() < deadline:
            assert self.proc.stderr is not None
            stderr_fd = self.proc.stderr.fileno()
            readers = [self.master]
            if not self.stderr_eof: readers.append(stderr_fd)
            for fd in select.select(readers, [], [], max(0, deadline-time.monotonic()))[0]:
                try: incoming = os.read(fd, 65536)
                except OSError as exc:
                    if fd == self.master and exc.errno == 5: continue
                    raise
                if fd == stderr_fd:
                    if not incoming: self.stderr_eof = True
                    self.stderr_raw.extend(incoming)
                else: chunk.extend(incoming)
        self.raw.extend(chunk)
        return bytes(chunk)

    def until(self, token, timeout=4):
        token = token.encode() if isinstance(token, str) else token
        start = len(self.raw)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.collect(min(0.1, max(0, deadline-time.monotonic())))
            if token in bytes(self.raw[start:]): return bytes(self.raw[start:])
            if self.proc.poll() is not None: break
        raise AssertionError(f'PTY missing {token!r}; rc={self.proc.poll()}; tail={bytes(self.raw[-3000:])!r}')

    def key(self, key): os.write(self.master, key.encode())

    def close(self, how: str | int = 'q'):
        # Idempotent cleanup returns the recorded failure, never a graceful fiction.
        if self.closed: return self.receipt
        started = time.time_ns()
        failures = []
        after = None
        forced = timed_out = False
        closed_fds = []
        stderr_closed = False
        try:
            if self.proc.poll() is None:
                if how == 'q': self.key('q')
                else: self.proc.send_signal(int(how))
            deadline = time.monotonic() + 3
            # Output and stderr may both backpressure the owned child. Never wait
            # for exit before draining, and never reset/extend this deadline.
            while self.proc.poll() is None and time.monotonic() < deadline:
                self.collect(min(.05, max(0, deadline-time.monotonic())))
            if self.proc.poll() is None:
                timed_out = True
                failures.append(AssertionError('owned PTY did not shut down'))
        except BaseException as exc:
            failures.append(exc)
        finally:
            try:
                if self.proc.poll() is None:
                    forced = True
                    self.proc.kill()
                self.proc.wait(timeout=3)
                self.collect(.1)
            except BaseException as exc:
                failures.append(exc)
            try: after = termios.tcgetattr(self.slave)
            except BaseException as exc: failures.append(exc)
            for fd in (self.master, self.slave):
                try:
                    os.close(fd)
                    try: os.fstat(fd)
                    except OSError as exc:
                        if exc.errno != 9: raise
                        closed_fds.append(fd)
                except BaseException as exc: failures.append(exc)
            try:
                assert self.proc.stderr is not None
                self.proc.stderr.close()
                stderr_closed = self.proc.stderr.closed
            except BaseException as exc: failures.append(exc)
            self.receipt = {'pid': self.proc.pid, 'started_ns': self.started_ns,
                            'argv': self.proc.args, 'environment': child_env(self.root),
                            'exit': self.proc.returncode, 'stderr': self.stderr_raw.decode('utf-8', errors='replace'),
                            'termios_before': self.before, 'termios_after': after,
                            'exact_restored': self.before == after if after is not None else None,
                            'semantic_restored': semantic(self.before) == semantic(after) if after is not None else None,
                            'pendin_before': bool(self.before[3] & getattr(termios, 'PENDIN', 0)),
                            'pendin_after': bool(after[3] & getattr(termios, 'PENDIN', 0)) if after is not None else None,
                            'cursor_shown': b'\x1b[?25h' in self.raw,
                            'alternate_left': b'\x1b[?1049l' in self.raw,
                            'reaped': self.proc.returncode is not None,
                            'forced_kill': forced, 'timed_out': timed_out, 'close_how': how,
                            'close_deadline_seconds': 3, 'close_started_ns': started,
                            'close_ended_ns': time.time_ns(), 'fds_closed': len(closed_fds) == 2,
                            'stderr_closed': stderr_closed,
                            'failures': [{'type': type(e).__name__, 'message': str(e)} for e in failures]}
            self.closed = True
            evidence = os.environ.get('COMPANY_TUI_TEST_EVIDENCE')
            if evidence:
                directory = Path(evidence); directory.mkdir(parents=True, exist_ok=True)
                name = f'pty-{self.proc.pid}'
                (directory / (name + '.raw')).write_bytes(self.raw)
                (directory / (name + '.stderr.raw')).write_bytes(self.stderr_raw)
                serializable = json.loads(json.dumps(self.receipt, default=lambda value: {'type': 'bytes', 'bytes_hex': value.hex()}))
                dump(directory / (name + '.json'), serializable)
        if failures:
            for failure in failures[1:]: failures[0].add_note(repr(failure))
            raise failures[0]
        return self.receipt


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.manifest, self.record, self.claims, self.plan = fixture(self.root, count=14)
        self.snapshot = data.load_snapshot(self.root / 'view.json')

    def test_p07_cell_bounded_actual_product_sizes(self):
        for w, h in [(80,12),(120,20),(48,12),(80,24),(120,40),(20,4),(1,1)]:
            for mode in ('org','flow','combined'):
                frame = tui.render_frame(self.snapshot, w, h, mode)
                self.assertLessEqual(len(frame.splitlines()), h)
                for line in frame.splitlines(): self.assertLessEqual(tui.cell_width(line), max(1,w-1))
                self.assertNotIn('\x1b', frame)

    def test_p07_fields_org_labels_and_flow_links(self):
        from test_status_tui_wide import reconstruct
        frame, meta = tui.render_details(self.snapshot, 120, 20)
        for text in ('코드', '전문가 미확인', '▶', '실행 관측 없음'):
            self.assertIn(text, frame)
        self.assertTrue(meta['nodes'])
        for node in meta['nodes']:
            self.assertEqual(reconstruct(frame, node), node['expected_fields'])
            self.assertEqual(reconstruct(frame, node)['model'], '모델명 미확인 · 할당 ID:fixture-model')
        organization = tui.render_frame(self.snapshot,120,20,mode='org')
        for text in ('lead:', 'member:'):
            self.assertIn(text, organization)
        self.assertNotIn('lead:',frame)  # compact task lanes do not repeat roster
        self.assertNotIn('inspector', frame.lower())
        self.assertIn('목표', frame)

    def test_p08_paging_all_tasks_reachable(self):
        pages = tui.page_count(self.snapshot, 80, 12, 'combined')
        self.assertGreater(pages, 1)
        frames = [tui.render_frame(self.snapshot,80,12,page=i) for i in range(pages)]
        reached = {node['task'] for i in range(pages) for node in tui.render_details(self.snapshot,80,12,page=i)[1]['nodes']}
        self.assertEqual(reached, {task['id'] for task in self.snapshot['tasks']})
        for task in self.snapshot['tasks']:
            state = tui.navigation.State(selected=task['id'], screen='source')
            view = tui._view(self.snapshot,80,12,'wide',state,False)
            self.assertIn('"id": "'+task['id']+'"', ''.join(row for page in view['pages'] for row in page))
        self.assertNotEqual(frames[0],frames[1])
        self.assertIn('page:',frames[0])

    def test_p08_control_injection_and_ascii(self):
        self.snapshot['tasks'][0]['title'] = 'safe\x1b[2J\n\r\x9b31m\u202eevil'
        frame = tui.render_frame(self.snapshot,80,12)
        self.assertNotIn('\x1b',frame); self.assertNotIn('\x9b',frame); self.assertNotIn('\u202e',frame)
        ascii_frame = tui.ascii_text(frame)
        self.assertTrue(ascii_frame.isascii())

    def test_p08_short_and_empty(self):
        frame = tui.render_frame(self.snapshot,80,4)
        self.assertIn('확대',frame)
        self.assertTrue(frame.startswith('q 종료'))
        self.assertNotIn('n/p',frame)
        self.assertEqual(tui.page_count(self.snapshot,80,4),1)
        self.snapshot['tasks'] = []; self.snapshot['organization'] = None
        frame = tui.render_frame(self.snapshot,80,12)
        self.assertIn('조직 미기록',frame); self.assertIn('작업 없음',frame)

    def test_p09_refresh_digest_ignores_generation_clock(self):
        controller = tui.RefreshState(self.root / 'view.json', interval=.25)
        self.assertTrue(controller.refresh(0))
        self.assertFalse(controller.refresh(.25))
        good = controller.snapshot
        (self.root / 'view.json').write_text('{')
        self.assertTrue(controller.refresh(.75))
        self.assertIs(controller.snapshot, good)
        self.assertIsNotNone(controller.error)
        self.assertGreaterEqual(controller.next_read,5.75)
        dump(self.root / 'view.json',self.manifest)
        self.assertFalse(controller.refresh(1))
        self.assertTrue(controller.refresh(6))
        self.assertIsNone(controller.error)

    def test_cli_once_json_and_errors(self):
        def run(*args):
            return subprocess.run([sys.executable,'-B',str(SCRIPT),'--manifest',str(self.root/'view.json'),*args],
                                  capture_output=True,text=True,env=child_env(self.root),timeout=10)
        result = run('--once','--json'); self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['schema'],'company-status-tui/v1')
        for args in [('--json',),('--interval','0.1'),('--interval','nan'),('--width','80'),('--once','--width','0')]:
            self.assertEqual(run(*args).returncode,2,args)
        self.manifest['binding']['revision'] = 'wrong'; dump(self.root/'view.json',self.manifest)
        self.assertEqual(run('--once').returncode,2)


class PTYTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.manifest, self.record, self.claims, self.plan = fixture(self.root, count=6)

    def assert_closed(self, receipt):
        self.assertEqual(receipt['exit'],0,receipt)
        self.assertTrue(receipt['semantic_restored'],receipt)
        self.assertTrue(receipt['cursor_shown'],receipt)
        self.assertTrue(receipt['alternate_left'],receipt)
        self.assertTrue(receipt['reaped'],receipt)
        self.assertTrue(receipt['fds_closed'],receipt)

    def synthetic_child(self, body):
        # Harness lifecycle fixture ONLY; this never stands for the actual viewer.
        from unittest.mock import patch
        script = self.root / 'synthetic-child.py'
        script.write_text("import os, signal, sys\nfrom pathlib import Path\n"
                          "root=Path(sys.argv[sys.argv.index('--manifest')+1]).parent\n"
                          "signal.signal(signal.SIGTERM, lambda *_: None)\n"
                          "(root/'ready').write_text(str(os.getpid()))\n" + body)
        with patch.object(sys.modules[__name__], 'SCRIPT', script):
            terminal = OwnedPTY(self.root)
        self.addCleanup(terminal.close)
        deadline = time.monotonic() + 3
        while not (self.root/'ready').exists() and time.monotonic() < deadline: time.sleep(.01)
        self.assertEqual((self.root/'ready').read_text(), str(terminal.proc.pid))
        return terminal

    def test_owned_synthetic_backlog_graceful_drain(self):
        terminal = self.synthetic_child("for fd, byte in [(1,b'B'),(2,b'E')]:\n pending=byte*(2*1024*1024)\n while pending: pending=pending[os.write(fd,pending):]\n")
        receipt = terminal.close(signal.SIGTERM)
        self.assertEqual(receipt['exit'], 0, receipt)
        self.assertEqual(bytes(terminal.raw), b'B'*(2*1024*1024))
        self.assertEqual(bytes(terminal.stderr_raw), b'E'*(2*1024*1024))
        self.assertFalse(receipt['forced_kill'], receipt)
        self.assertFalse(receipt['timed_out'], receipt)
        self.assertEqual(receipt['failures'], [])
        for key in ('reaped', 'fds_closed', 'stderr_closed', 'semantic_restored'):
            self.assertTrue(receipt[key], receipt)
        self.assertIs(terminal.close(), receipt)

    def test_owned_synthetic_timeout_receipt_and_double_cleanup(self):
        terminal = self.synthetic_child("os.write(1,b'owned-timeout')\nos.write(2,b'owned-stderr')\nwhile True: signal.pause()\n")
        started = time.monotonic()
        with self.assertRaisesRegex(AssertionError, 'owned PTY did not shut down'):
            terminal.close(signal.SIGTERM)
        elapsed = time.monotonic() - started
        receipt = terminal.receipt
        self.assertGreaterEqual(elapsed, 3)
        self.assertLess(elapsed, 6)
        self.assertTrue(receipt['timed_out'], receipt)
        self.assertTrue(receipt['forced_kill'], receipt)
        self.assertEqual(receipt['exit'], -signal.SIGKILL)
        self.assertEqual(receipt['close_deadline_seconds'], 3)
        self.assertIn(b'owned-timeout', terminal.raw)
        self.assertEqual(receipt['stderr'], 'owned-stderr')
        self.assertEqual(receipt['failures'][0]['type'], 'AssertionError')
        self.assertIsNotNone(receipt['termios_after'])
        for key in ('reaped', 'fds_closed', 'stderr_closed'):
            self.assertTrue(receipt[key], receipt)
        self.assertIs(terminal.close(), receipt)
        self.assertIs(terminal.close(signal.SIGINT), receipt)

    def test_owned_repeated_close_actual_viewer(self):
        terminal = OwnedPTY(self.root)
        self.addCleanup(terminal.close)
        terminal.until('page:1/')
        receipt = terminal.close()
        self.assert_closed(receipt)
        self.assertFalse(receipt['forced_kill'], receipt)
        self.assertEqual(receipt['failures'], [])
        self.assertIs(terminal.close(), receipt)
        self.assertIs(terminal.close(signal.SIGTERM), receipt)

    def test_p08_p10_owned_80x12_navigation_resize_no_color_q(self):
        terminal = OwnedPTY(self.root)
        self.addCleanup(terminal.close)
        terminal.until('page:1/')
        paint = b'\x1b[H\x1b[2J'
        before = terminal.raw.count(paint)
        terminal.collect(.7)
        self.assertEqual(terminal.raw.count(paint), before, 'unchanged data repainted')
        terminal.key('n'); terminal.until('page:2/')
        terminal.key('p'); terminal.until('page:1/')
        terminal.key('o'); terminal.until('[org]')
        terminal.key('f'); terminal.until('[flow]')
        terminal.key('c'); terminal.until('[combined]')
        terminal.resize(120,20); terminal.until('전문가')
        terminal.resize(48,12); terminal.until('전문')
        terminal.resize(80,4); terminal.until('확대')
        self.assertNotRegex(bytes(terminal.raw),rb'\x1b\[[0-9;]*m')
        self.assert_closed(terminal.close())

    def test_p09_p10_actual_update_error_last_good_recovery_sigterm(self):
        terminal = OwnedPTY(self.root,120,20)
        self.addCleanup(terminal.close)
        terminal.until('모델명 미확인')
        self.manifest['tasks'][0]['title'] = '갱신 확인'
        dump(self.root/'view.json',self.manifest)
        terminal.until('갱신 확인',timeout=4)
        (self.root/'view.json').write_text('{')
        output = terminal.until('ERROR',timeout=4)
        self.assertIn('갱신 확인'.encode(),output)
        self.assertIn(b'last-good',output)
        self.manifest['tasks'][0]['title'] = '복구 확인'
        dump(self.root/'view.json',self.manifest)
        terminal.until('복구 확인',timeout=7)
        self.assert_closed(terminal.close(signal.SIGTERM))

    def test_p10_initial_error_exit_and_ctrl_c_restore(self):
        (self.root/'view.json').write_text('{')
        terminal = OwnedPTY(self.root); self.addCleanup(terminal.close)
        terminal.proc.wait(timeout=5)
        receipt = terminal.close()
        self.assertEqual(receipt['exit'],2)
        self.assertTrue(receipt['semantic_restored'])
        dump(self.root/'view.json',self.manifest)
        second = OwnedPTY(self.root, extra=('--ascii',)); self.addCleanup(second.close)
        second.until('[combined]')
        self.assertTrue(re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]',b'',bytes(second.raw)).isascii())
        second.key('\x03')
        # Under this isolated Popen PTY there is no foreground session to receive
        # VINTR, so send the actual signal too; host controlling-PTY behavior differs.
        self.assert_closed(second.close(signal.SIGINT))


if __name__ == '__main__': unittest.main()
