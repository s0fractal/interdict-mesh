#!/usr/bin/env python3
"""The review record a pull request needs before merge (AGENTS.md "Review", ADR-0032).

A record is a pull-request review or an issue comment on the pull request whose body has,
each on a line of its own, `review-of: <full head sha>` and `verdict: ACCEPT` or
`verdict: AMEND`. The check passes when, for the pull request's current head, at least one
record says ACCEPT and no reviewer's last word is AMEND, counting only records whose author
is a login in the allowlist (.github/review-allowlist) and is not the pull request's author.
Anything else fails and names the head a review has to cite: a record of an earlier head is
stale, a login outside the allowlist or the author's own record does not count.

    python3 -I scripts/check-review.py --pull pull.json --comments comments.json \
        [--reviews reviews.json] --allowlist .github/review-allowlist
    python3 -I scripts/check-review.py --head SHA --author LOGIN --comments ... --allowlist ...

pull.json is `gh api repos/{r}/pulls/{n}` (head.sha, user.login); comments.json and reviews.json
are `gh api --paginate` of issues/{n}/comments and pulls/{n}/reviews, as one array, as the
concatenated arrays --paginate prints, or as one object per line. Standard library only, and
nothing here runs a command: bodies and logins are untrusted text and stay data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

REVIEW_OF = re.compile(r"^[ \t]*review-of:[ \t]*([0-9a-fA-F]{40})[ \t]*$", re.M)
VERDICT = re.compile(r"^[ \t]*verdict:[ \t]*([A-Za-z]+)[ \t]*$", re.M)
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
VERDICTS = ("ACCEPT", "AMEND")
MAX_RECORDS = 10_000  # comments and reviews read per pull request; more is refused, not sampled


class Record:
    """One review or comment, as the check sees it."""

    def __init__(self, kind: str, ident: object, login: str, body: str, at: str, state: str = ""):
        self.kind, self.ident, self.login, self.body, self.at, self.state = kind, ident, login, body, at, state

    def where(self) -> str:
        return f"{self.kind} {self.ident} by {self.login or '<no login>'}"


def read_values(path: Path) -> list:
    """Every JSON value in the file, flattened: an array, concatenated arrays, or lines."""
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    out, pos, n = [], 0, len(text)
    while True:
        while pos < n and text[pos].isspace():
            pos += 1
        if pos >= n:
            return out
        value, pos = decoder.raw_decode(text, pos)
        out.extend(value if isinstance(value, list) else [value])
        if len(out) > MAX_RECORDS:
            raise ValueError(f"{path}: more than {MAX_RECORDS} records")


def login_of(item: dict) -> str:
    user = item.get("user") or {}
    login = user.get("login") if isinstance(user, dict) else None
    return login.lower() if isinstance(login, str) else ""


def records(comments: list, reviews: list) -> list[Record]:
    out = []
    for c in comments:
        if isinstance(c, dict):
            out.append(Record("comment", c.get("id"), login_of(c), str(c.get("body") or ""),
                              str(c.get("created_at") or "")))
    for r in reviews:
        if isinstance(r, dict):
            out.append(Record("review", r.get("id"), login_of(r), str(r.get("body") or ""),
                              str(r.get("submitted_at") or ""), str(r.get("state") or "").upper()))
    # GitHub's timestamps are ISO-8601 UTC, so text order is time order; ties by kind and id.
    out.sort(key=lambda x: (x.at, x.kind, str(x.ident)))
    return out


def read_allowlist(path: Path) -> set[str]:
    """One login per line, `#` comments and blank lines ignored; a line that is not a login
    is an error: a mistyped allowlist fails closed, it does not admit nobody by accident."""
    logins = set()
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not LOGIN.fullmatch(line):
            raise ValueError(f"{path}:{n}: {line!r} is not a GitHub login")
        logins.add(line.lower())
    return logins


def evaluate(head: str, author: str, items: list[Record], allowlist: set[str],
             allowlist_name: str = ".github/review-allowlist") -> tuple[bool, list[str]]:
    """(passed, report lines). The first line is the verdict; the rest say why."""
    head, author = head.lower(), author.lower()
    notes: list[str] = []
    last: dict[str, tuple[str, Record]] = {}  # reviewer -> (verdict, record) on this head
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        return False, [f"agent-review: FAIL the head {head!r} is not a full commit sha"]
    if not allowlist:
        notes.append(f"the allowlist {allowlist_name} names nobody: no review can count")
    for rec in items:
        if rec.kind == "review" and rec.state in ("DISMISSED", "PENDING"):
            continue
        m_of, m_verdict = REVIEW_OF.search(rec.body), VERDICT.search(rec.body)
        if not m_of and not m_verdict:
            continue  # conversation, not a record
        if not m_of or not m_verdict:
            notes.append(f"{rec.where()}: has only one of the two lines review-of: / verdict:")
            continue
        cited, verdict = m_of.group(1).lower(), m_verdict.group(1).upper()
        if verdict not in VERDICTS:
            notes.append(f"{rec.where()}: verdict {verdict} is not ACCEPT or AMEND")
            continue
        if cited != head:
            notes.append(f"{rec.where()}: stale, it reviews {cited}; the head is {head}")
            continue
        if rec.login == author:
            notes.append(f"{rec.where()}: a self-review by the pull request's author does not count")
            continue
        if rec.login not in allowlist:
            notes.append(f"{rec.where()}: {rec.login or '<no login>'} is not in {allowlist_name}")
            continue
        last[rec.login] = (verdict, rec)
    accepts = [r for v, r in last.values() if v == "ACCEPT"]
    amends = [r for v, r in last.values() if v == "AMEND"]
    if accepts and not amends:
        return True, [f"agent-review: PASS ACCEPT for head {head} ({', '.join(r.where() for r in accepts)})"] + notes
    lines = [f"agent-review: FAIL no ACCEPT review of the current head {head}"]
    lines += [f"{r.where()}: AMEND on this head" for r in amends]
    lines += notes
    lines.append(f"a review has to carry the lines `review-of: {head}` and `verdict: ACCEPT`, "
                 f"posted by a login in {allowlist_name} other than the author {author}")
    return False, lines


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--pull", type=Path, help="gh api repos/{r}/pulls/{n}: head.sha and user.login")
    p.add_argument("--head", help="the pull request's current head sha (instead of --pull)")
    p.add_argument("--author", help="the pull request author's login (instead of --pull)")
    p.add_argument("--comments", type=Path, required=True, help="issue comments of the pull request")
    p.add_argument("--reviews", type=Path, help="pull-request reviews of the pull request")
    p.add_argument("--allowlist", type=Path, required=True, help="logins whose reviews count")
    a = p.parse_args(argv)
    try:
        if a.pull is not None:
            pull = json.loads(a.pull.read_text(encoding="utf-8"))
            head = str((pull.get("head") or {}).get("sha") or "")
            author = login_of(pull)
        elif a.head and a.author:
            head, author = a.head, a.author
        else:
            p.error("--pull, or both --head and --author")
        items = records(read_values(a.comments), read_values(a.reviews) if a.reviews else [])
        allowlist = read_allowlist(a.allowlist)
    except (OSError, ValueError) as e:
        print(f"agent-review: FAIL cannot read the inputs: {e}")
        return 2
    ok, lines = evaluate(head, author, items, allowlist, a.allowlist.as_posix())
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
