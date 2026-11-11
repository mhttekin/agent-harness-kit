# <Goal>

## Scope and evidence
<Desired outcome, baseline, accepted golden hashes and relevant ADRs.>

## Rules for coding sessions
1. Read AGENTS.md, this plan, progress.md, features.json and recent Git history.
   Run init.sh and stop if the baseline fails; do not fix unrelated gates.
2. Do exactly the first pending unit whose dependencies pass. Keep it small;
   split an oversized unit and stop for inspection.
3. Preserve protected labels and accepted goldens. Test behavior through real
   domain logic with external seams mocked. No unrelated cleanup.
4. Run check.sh and review the complete diff including new files using the review
   skill. Fix concrete findings and record evidence in progress.md.
5. Under run_units.sh, leave everything unstaged and uncommitted, including queue
   status. The loop verifies, updates status, stages explicit paths and commits.
   Never push, reset, stash or commit from a child session. On failure the loop
   stops and preserves changes for inspection; do not auto-restore them.
6. A manual session owns its own explicit staging/review/commit per project policy.
   Never bypass hooks. Record tests, remaining risks and next steps, then stop.

## Completion
<Observable acceptance criteria and evaluation thresholds.>
