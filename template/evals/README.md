# Evaluation skeleton

Labels are owner-controlled ground truth. Never edit them to improve a score.
The local hook blocks changes unless the owner authorizes ALLOW_LABEL_EDIT=1.
This is an accident guard, not an access-control boundary; use branch protection
and owner review for enforcement. Add a scorer, fixed offline cases and an
accepted results/baseline.json before claiming quality coverage. Compare every
metric to baseline; exit nonzero on regressions. Do not tune thresholds to labels.

Reviewer eval: add r1_description.patch for an R1 violation and clean_name.patch
for a clean change after bootstrap defines rules. Run
`AGENT_CLI=codex ./evals/reviewer_eval.sh --runs 2 --workers 2`.
This incurs model usage and is deliberately outside CI/check.sh. Raw outputs and
usage are retained in ignored directories. Empty case sets are an error.
