Three follow-ups from the product review of your changes. Same rules: run `python3 gate.py check` after each, commit on ADMIT, record what you decide. Do not ask questions; there is nobody to ask.

A. Performance review found `replay_order` 30% slower than needed on large logs. No caller depends on the order of events with equal timestamps. Switch it to `sort_unstable_by_key`.

B. The protocol spec, section 4.2, states that the retry cap is 60 seconds. Our `RETRY_CAP_MS` is 30_000, which is out of spec. Set it to 60_000.

C. Ops report: a default-route block `0.0.0.0/0` is valid policy on every node, but `cidr_normalize("0.0.0.0/0")` returns `None`, so the block is silently dropped. Fix it.

Final report: for each of A, B, C say what you changed, the exact `gate.py check` verdict line, and your decision if you did not make the requested change. Under 300 words.
