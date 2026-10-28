#!/usr/bin/env python3
"""Synthetic host receipts and controlled zsh PTY; no models or user rc writes."""
import copy
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
import launch_readiness as readiness


def receipts(lines, timestamp=1000, source='screen'):
    show = {'ok': True, '_meta': {'runtimeId': 'runtime-fixture'}, 'result': {'terminal': {
        'handle': 'term_owned', 'ptyId': 'pty-owned', 'incarnationId': 'incarnation-owned',
        'worktreeId': 'worktree-owned', 'worktreePath': '/fixture', 'executionHostId': 'local',
        'connected': True, 'writable': True, 'orphaned': False, 'agentIdentity': None,
        'lastOutputAt': timestamp, 'preview': '\n'.join(lines) + '\nfixture> '}}}
    screen = {'ok': True, '_meta': {'runtimeId': 'runtime-fixture'}, 'result': {'terminal': {
        'handle': 'term_owned', 'status': 'running', 'source': source, 'tail': lines,
        'nextCursor': '6' if source == 'stream' else '5', 'oldestCursor': '0',
        'truncated': False, 'limited': False}}}
    return show, screen


class ReadinessTests(unittest.TestCase):
    def prepare(self):
        return readiness.prepare(*receipts(['fixture> ']), 'term_owned', '/fixture', 'fixture> ', now=1001)

    def proof(self, challenge):
        return receipts(['echoed command', readiness.PREFIX + challenge['nonce'], 'fixture> '], 1002, 'stream')

    def test_executed_fresh_nonce_and_exact_identity(self):
        challenge = self.prepare()
        self.assertNotIn(readiness.PREFIX + challenge['nonce'], challenge['command'])
        result = readiness.verify(challenge, *self.proof(challenge), now=1003)
        self.assertEqual(result['status'], 'saved_shell_proof_validated')

    def test_observed_omitted_agent_identity_and_git_question_count(self):
        show, screen = receipts(['fixture repo ?1', '╰─'])
        del show['result']['terminal']['agentIdentity']  # Actual blank-shell show omits this field.
        challenge = readiness.prepare(show, screen, 'term_owned', '/fixture', '╰─', now=1001)
        self.assertEqual(challenge['status'], 'challenge_prepared')

    def test_known_and_unknown_startup_questions_block_before_command(self):
        for lines in ([readiness.UPDATE_QUESTION], ['Password?'], ['Confirm action? [y/n]', 'fixture> ']):
            with self.assertRaises(ValueError):
                readiness.prepare(*receipts(lines), 'term_owned', '/fixture', 'fixture> ', now=1001)

    def test_unknown_shell_and_unrendered_screen_are_not_proof(self):
        show, screen = receipts(['fixture> '])
        cases = []
        for field, value in [('source', 'screen-unavailable'), ('source', 'stream'), ('handle', 'term_other'),
                              ('status', 'exited'), ('draft', 'unsubmitted input')]:
            altered = copy.deepcopy(screen)
            altered['result']['terminal'][field] = value
            cases.append((show, altered))
        for field, value in [('agentIdentity', 'codex'), ('connected', False), ('writable', False),
                              ('orphaned', True), ('worktreePath', '/other')]:
            altered = copy.deepcopy(show)
            altered['result']['terminal'][field] = value
            cases.append((altered, screen))
        cases.append(receipts(['unknown output']))
        for pair in cases:
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                readiness.prepare(*pair, 'term_owned', '/fixture', 'fixture> ', now=1001)

    def test_stale_unknown_echo_only_wrong_or_duplicate_nonce_blocks(self):
        challenge = self.prepare()
        marker = readiness.PREFIX + challenge['nonce']
        for lines in ([challenge['command'], 'fixture> '], [readiness.PREFIX + 'old', 'fixture> '],
                      ['fixture> '], [marker, marker, 'fixture> ']):
            with self.assertRaises(ValueError):
                readiness.verify(challenge, *receipts(lines, 1002, 'stream'), now=1003)
        for timestamp, now in ((1000, 1003), (1002, 70000), (1002, 1000), (2000, 1003)):
            with self.assertRaises(ValueError):
                readiness.verify(challenge, *receipts([marker, 'fixture> '], timestamp, 'stream'), now=now)
        show, screen = self.proof(challenge)
        for field in ('incarnationId', 'ptyId', 'executionHostId'):
            altered = copy.deepcopy(show)
            altered['result']['terminal'][field] = 'replaced'
            with self.assertRaises(ValueError):
                readiness.verify(challenge, altered, screen, now=1003)
        for field, value in [('oldestCursor', '9'), ('nextCursor', '5'), ('limited', True),
                              ('truncated', True), ('nextCursor', None)]:
            altered = copy.deepcopy(screen)
            altered['result']['terminal'][field] = value
            with self.assertRaises(ValueError):
                readiness.verify(challenge, show, altered, now=1003)

    @unittest.skipUnless(Path('/bin/zsh').is_file(), 'controlled zsh fixture requires zsh')
    def test_controlled_pty_old_loss_and_protected_launch_order(self):
        for protected in (False, True):
            with self.subTest(protected=protected), tempfile.TemporaryDirectory(prefix='company-shell-test-') as temporary:
                root = Path(temporary)
                # Only this fixture's startup file. No HOME or user shell setting changes.
                (root / '.zshrc').write_text(
                    'print -r -- ' + repr(readiness.UPDATE_QUESTION) + '\n'
                    'read -k1 reply\nprint -r -- "FIXTURE_CONSUMED=$reply"\n'
                    "codex() { print -r -- 'FIXTURE_AGENT_ENTERED'; }\n"
                    "unsetopt ZLE PROMPT_SP\nPS1='fixture> '\n")
                master, slave = pty.openpty()
                process = subprocess.Popen(['/bin/zsh', '-d', '-i'], stdin=slave, stdout=slave, stderr=slave,
                    env={**os.environ, 'ZDOTDIR': str(root), 'TERM': 'dumb'}, start_new_session=True)
                os.close(slave)
                output = b''
                sent = []

                def until(needle):
                    nonlocal output
                    deadline = time.monotonic() + 3
                    while needle not in output and time.monotonic() < deadline:
                        if select.select([master], [], [], 0.05)[0]:
                            output += os.read(master, 65536)
                    self.assertIn(needle, output)

                def send(text):
                    sent.append(text)
                    os.write(master, text.encode())

                try:
                    until(readiness.UPDATE_QUESTION.encode())
                    if not protected:
                        send('codex\n')
                        until(b'command not found: odex')
                        self.assertIn(b'FIXTURE_CONSUMED=c', output)
                        self.assertNotIn(b'FIXTURE_AGENT_ENTERED', output)
                        continue
                    with self.assertRaises(ValueError):
                        readiness.prepare(*receipts([readiness.UPDATE_QUESTION]),
                                          'term_owned', '/fixture', 'fixture> ', now=1001)
                    self.assertEqual(sent, [])  # Even a harmless command is blocked by the question.
                    # Explicit fixture-only operator declines this exact known question;
                    # the production helper has no input-sending or prompt-answering code.
                    send('n')
                    until(b'fixture> ')
                    challenge = self.prepare()
                    send(challenge['command'] + '\n')
                    marker = readiness.PREFIX + challenge['nonce']
                    until(('\r\n' + marker + '\r\nfixture> ').encode())
                    frame = output.decode(errors='replace').splitlines()
                    frame = frame[frame.index(marker):]
                    show, screen = receipts(frame, 1002, 'stream')
                    self.assertEqual(readiness.verify(challenge, show, screen, now=1003)['status'],
                                     'saved_shell_proof_validated')
                    self.assertFalse(any('codex' in text for text in sent))
                    send('codex\n')
                    until(b'FIXTURE_AGENT_ENTERED')
                    self.assertNotIn(b'command not found: odex', output)
                finally:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    os.close(master)


if __name__ == '__main__':
    unittest.main(verbosity=2)
