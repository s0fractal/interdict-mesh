"""scripts/check-review.py: the review record a pull request needs before merge (AGENTS.md
"Review", ADR-0032). The check passes only on `review-of: <current head>` + `verdict: ACCEPT`
by an allowlisted login other than the author; a stale head, a self-review, AMEND, a login
outside the allowlist or an empty allowlist fail and name the head to cite.

    python3 scripts/test_check_review.py
"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'check-review.py'
spec = importlib.util.spec_from_file_location('check_review', SCRIPT)
check_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_review)

HEAD = 'a' * 40
OLD = 'b' * 40
AUTHOR = 'agent-author'
REVIEWER = 'agent-reviewer'
ALLOW = {REVIEWER, 's0fractal'}


def body(sha, verdict, before='', after=''):
    return f'{before}review-of: {sha}\nverdict: {verdict}\n{after}'


def comment(login, text, ident=1, at='2026-10-20T10:00:00Z'):
    return {'id': ident, 'user': {'login': login}, 'body': text, 'created_at': at}


def review(login, text, ident=1, at='2026-10-20T10:00:00Z', state='COMMENTED'):
    return {'id': ident, 'user': {'login': login}, 'body': text, 'submitted_at': at, 'state': state}


def run(comments=(), reviews=(), head=HEAD, author=AUTHOR, allowlist=ALLOW):
    items = check_review.records(list(comments), list(reviews))
    return check_review.evaluate(head, author, items, set(allowlist))


class Verdicts(unittest.TestCase):
    def test_accept_on_the_current_head_by_an_allowlisted_reviewer_passes(self):
        ok, lines = run([comment(REVIEWER, body(HEAD, 'ACCEPT'))])
        self.assertTrue(ok, lines)
        self.assertIn('PASS', lines[0])
        self.assertIn(HEAD, lines[0])

    def test_a_pull_request_review_counts_like_a_comment(self):
        ok, lines = run(reviews=[review(REVIEWER, body(HEAD, 'ACCEPT', before='Findings: none.\n\n'))])
        self.assertTrue(ok, lines)

    def test_no_record_fails_naming_the_expected_head(self):
        ok, lines = run([comment(REVIEWER, 'looks fine to me')])
        self.assertFalse(ok)
        self.assertIn(f'review-of: {HEAD}', lines[-1])
        self.assertIn('verdict: ACCEPT', lines[-1])

    def test_a_review_of_an_earlier_head_is_stale(self):
        ok, lines = run([comment(REVIEWER, body(OLD, 'ACCEPT'))])
        self.assertFalse(ok)
        self.assertTrue(any('stale' in l and OLD in l and HEAD in l for l in lines), lines)

    def test_a_login_outside_the_allowlist_does_not_count(self):
        ok, lines = run([comment('passer-by', body(HEAD, 'ACCEPT'))])
        self.assertFalse(ok)
        self.assertTrue(any('passer-by is not in' in l for l in lines), lines)

    def test_an_empty_allowlist_admits_nobody(self):
        ok, lines = run([comment(REVIEWER, body(HEAD, 'ACCEPT'))], allowlist=set())
        self.assertFalse(ok)
        self.assertTrue(any('names nobody' in l for l in lines), lines)

    def test_the_authors_own_review_is_a_self_review(self):
        ok, lines = run([comment(REVIEWER, body(HEAD, 'ACCEPT'))], author=REVIEWER)
        self.assertFalse(ok)
        self.assertTrue(any('self-review' in l for l in lines), lines)

    def test_amend_fails(self):
        ok, lines = run([comment(REVIEWER, body(HEAD, 'AMEND', after='- F1: the bound is guessed\n'))])
        self.assertFalse(ok)
        self.assertTrue(any('AMEND on this head' in l for l in lines), lines)

    def test_a_reviewers_last_word_on_the_head_counts(self):
        amend = comment(REVIEWER, body(HEAD, 'AMEND'), 1, '2026-10-20T10:00:00Z')
        accept = comment(REVIEWER, body(HEAD, 'ACCEPT'), 2, '2026-10-20T11:00:00Z')
        self.assertTrue(run([accept, amend])[0])  # order in the file does not matter
        later_amend = comment(REVIEWER, body(HEAD, 'AMEND'), 3, '2026-10-20T12:00:00Z')
        self.assertFalse(run([amend, accept, later_amend])[0])

    def test_another_reviewers_amend_blocks_an_accept(self):
        ok, _ = run([comment(REVIEWER, body(HEAD, 'ACCEPT'), 1),
                     comment('s0fractal', body(HEAD, 'AMEND'), 2, '2026-10-20T11:00:00Z')])
        self.assertFalse(ok)

    def test_a_dismissed_review_is_not_a_record(self):
        ok, _ = run(reviews=[review(REVIEWER, body(HEAD, 'ACCEPT'), state='DISMISSED')])
        self.assertFalse(ok)

    def test_an_unknown_verdict_or_a_lone_line_is_reported_not_counted(self):
        ok, lines = run([comment(REVIEWER, body(HEAD, 'LGTM')),
                         comment(REVIEWER, f'review-of: {HEAD}\n', 2)])
        self.assertFalse(ok)
        self.assertTrue(any('LGTM is not ACCEPT or AMEND' in l for l in lines), lines)
        self.assertTrue(any('only one of the two lines' in l for l in lines), lines)

    def test_logins_and_shas_compare_case_insensitively(self):
        ok, _ = run([comment(REVIEWER.upper(), body(HEAD.upper(), 'accept'))], head=HEAD.upper())
        self.assertTrue(ok)

    def test_a_deleted_account_has_no_login_and_does_not_count(self):
        ghost = {'id': 1, 'user': None, 'body': body(HEAD, 'ACCEPT'), 'created_at': ''}
        ok, lines = run([ghost])
        self.assertFalse(ok)
        self.assertTrue(any('<no login> is not in' in l for l in lines), lines)

    def test_a_short_head_is_refused(self):
        ok, lines = run([comment(REVIEWER, 'review-of: abc\nverdict: ACCEPT')], head='abc')
        self.assertFalse(ok)
        self.assertIn('not a full commit sha', lines[0])


class Inputs(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text)
        return path

    def test_an_array_concatenated_pages_and_json_lines_read_the_same(self):
        a, b = comment(REVIEWER, 'a', 1), comment(REVIEWER, 'b', 2)
        forms = [json.dumps([a, b]), json.dumps([a]) + json.dumps([b]),
                 json.dumps(a) + '\n' + json.dumps(b) + '\n']
        for text in forms:
            with self.subTest(text[:20]):
                self.assertEqual(check_review.read_values(self.write('c.json', text)), [a, b])

    def test_the_allowlist_ignores_comments_and_refuses_what_is_not_a_login(self):
        path = self.write('allow', '# owner\ns0fractal\n\nAgent-Two  # the reviewing agent\n')
        self.assertEqual(check_review.read_allowlist(path), {'s0fractal', 'agent-two'})
        with self.assertRaises(ValueError):
            check_review.read_allowlist(self.write('bad', 's0fractal\nnot a login\n'))

    def test_too_many_records_are_refused_not_sampled(self):
        many = json.dumps([comment(REVIEWER, 'x', i) for i in range(check_review.MAX_RECORDS + 1)])
        with self.assertRaises(ValueError):
            check_review.read_values(self.write('many.json', many))


class CommandLine(unittest.TestCase):
    """As the workflow runs it: python3 -I, files from `gh api`, exit 0 only on ACCEPT."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / 'pull.json').write_text(json.dumps({'head': {'sha': HEAD}, 'user': {'login': AUTHOR}}))
        (self.dir / 'allow').write_text('# adding a login is the owner\'s act\ns0fractal\n' + REVIEWER + '\n')
        (self.dir / 'reviews.json').write_text('[]')

    def check(self, comments, extra=()):
        (self.dir / 'comments.json').write_text(json.dumps(comments))
        return subprocess.run([sys.executable, '-I', str(SCRIPT), '--pull', str(self.dir / 'pull.json'),
                               '--comments', str(self.dir / 'comments.json'),
                               '--reviews', str(self.dir / 'reviews.json'),
                               '--allowlist', str(self.dir / 'allow'), *extra],
                              capture_output=True, text=True)

    def test_accept_exits_zero_and_anything_else_one(self):
        r = self.check([comment(REVIEWER, body(HEAD, 'ACCEPT'))])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('agent-review: PASS', r.stdout)
        r = self.check([comment(REVIEWER, body(OLD, 'ACCEPT'))])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f'review-of: {HEAD}', r.stdout)

    def test_head_and_author_may_replace_the_pull_file(self):
        (self.dir / 'comments.json').write_text(json.dumps([comment(REVIEWER, body(HEAD, 'ACCEPT'))]))
        r = subprocess.run([sys.executable, '-I', str(SCRIPT), '--head', HEAD, '--author', AUTHOR,
                            '--comments', str(self.dir / 'comments.json'),
                            '--allowlist', str(self.dir / 'allow')], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_an_unreadable_input_exits_two(self):
        r = self.check([comment(REVIEWER, body(HEAD, 'ACCEPT'))], extra=['--allowlist', str(self.dir / 'missing')])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('cannot read the inputs', r.stdout)


if __name__ == '__main__':
    unittest.main()
