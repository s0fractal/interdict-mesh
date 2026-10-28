# ADR-0032. The review record is a required check; agents merge behind it

Status: SUPERSEDED by ADR-0033 (2026-10-28): reviews are Warrant 3 records; the check, the
allowlist and the workflow are removed. Was: PROPOSED. The check, the allowlist and the code-owner file are in the tree; whether
the check is required, whether code-owner review is required and whether agents may merge
behind them are the owner's decisions, listed at the end. Nothing here is accepted until the
owner makes them. Date: 2026-10-20. Extends ADR-0023 (owner-pinned witnesses), ADR-0030
(trust root), ADR-0031 (responsibility).

## The gap

AGENTS.md "Review" says every pull request is reviewed by an agent before merge and that the
review belongs in the pull request, tied to the head it was about. Nothing checked it: of the
nine pull requests #50–#58 merged before this record, eight had no comment and no review at
all, and the one comment there was does not say which head it read. The rule was review-only,
and review-only rules are the ones that lapse. The 2026-10-20 industrial plan (wave 2) wants
agents to merge green, reviewed pull requests on their own while the owner keeps the trust
root; without a check that a review happened, "reviewed" is a word.

## Decision (proposed)

**The record.** A review is a pull-request review (`gh pr review <n> --comment
--body-file review.md`) or an issue comment on the pull request whose body carries, each
on its own line, `review-of: <full head sha>` and `verdict: ACCEPT` or `verdict: AMEND`,
with the findings under them. The sha binds the record to the bytes it was about: a new push
makes every earlier record stale, and the new head needs its own.

**The check.** The `agent-review` job (`.github/workflows/agent-review.yml`,
`scripts/check-review.py`, `scripts/test_check_review.py`) passes when, for the pull
request's current head, at least one record says ACCEPT and no reviewer's last word is
AMEND, counting only records by a login in `.github/review-allowlist` who is not the pull
request's author. It fails, naming the head to cite, on a missing or stale record, on AMEND,
on a self-review and on a login outside the allowlist. It runs on `pull_request_target`, so
the workflow, the checker and the allowlist are main's and a pull request cannot edit the
check it has to pass; nothing of the pull request is checked out or run, its comments and
reviews are read through the API as data with a read-only token. It runs again on
`pull_request_review` events, so a posted review turns the check green without a push.

**The allowlist.** `.github/review-allowlist`, one login per line, seeded with the owner.
Adding a login is the owner's act: the file is a trust-root path. Because a reviewer's record
never counts on their own pull request, and every pull request so far was opened under the
owner's login, the check as seeded cannot pass: a second login (the reviewing agent's own
account, or the authoring agent's) is the precondition for it to pass at all.

**Code owners.** `.github/CODEOWNERS` names the trust-root paths (the witness signers, the
pinned checker, the base gate workflow, the manifest and its signature, `docs/adr/`, the
allowlist, the code-owner file itself) and the agent-review workflow and checker. Enabling
"require review from code owners" in the protect-main ruleset is the owner's change; with it
on, a change to those paths needs the owner's approval, which GitHub never takes from the
author of the pull request.

**Merge.** Once `agent-review` is a required check, an agent may merge a pull request whose
required checks are all green, including `agent-review`, and that touches no trust-root
path. Trust-root paths stay the owner's merge, by the code-owner rule. This is the
delegation ADR-0031 describes, with a record behind it instead of a word.

## What the check does not establish

- That the review is any good. It establishes that a named login read a named head and
  wrote a verdict; the verdict's quality is what the allowlist is for.
- That the pull request's copy of `agent-review.yml` is main's on a review event. The
  `pull_request_review` event runs the pull request's workflow file, so a pull request that
  edits it could make its own check pass on a review event; `.github/CODEOWNERS` lists the
  file so that, with code-owner review on, such a pull request needs the owner. Until then,
  a pull request that touches the workflow or the checker is read by the owner by rule.
- That an issue comment was seen. A run an issue comment triggers would attach to main's
  head, not the pull request's, so the workflow does not listen to that event; a review event
  or a re-run of the job reads the comments that are there.

## Alternatives not taken

- `checks: write` and a check run created by an `issue_comment` run on the pull request's
  head: works, but gives the job a write scope the task excluded and ties the record to a
  check-run API call instead of the comment itself.
- A GitHub approval (`gh pr review --approve`) as the record: it does not carry the head
  sha in a form the checker can read back from the text, and the owner's ruleset has no
  approval count on purpose; the text line is explicit and survives a copy into a
  measurement folder.

## Owner decisions this record waits for

1. Add `agent-review` to the required status checks of the protect-main ruleset.
2. Enable "Require review from Code Owners" in the same ruleset.
3. Add the reviewing agent's login (or the authoring agent's) to `.github/review-allowlist`
   so that a review can count; until then the check cannot pass.
4. Accept that an agent merges a green, reviewed pull request that touches no trust-root
   path. Until this line is accepted, merging stays the owner's.
