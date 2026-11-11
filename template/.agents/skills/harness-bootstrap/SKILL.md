---
name: harness-bootstrap
description: Interview a project owner, establish minimal invariants, and derive tests and review rules.
---

# Bootstrap this project

1. Read the current repository, its README, test configuration and existing
   AGENTS.md. Never consult or copy another project's rules, examples, names,
   architecture, labels or constraints. Template example tests are demonstrations,
   not product requirements. Preserve established local rules unless the owner
   authorizes a change.
2. Interview the owner in small batches: What must always stay true? Which past
   failures must never recur? What must work without optional services? What data
   is protected, and who owns it? Which commands are canonical? What Git actions
   may an agent perform? Ask for concrete inputs and expected outcomes. Do not
   invent answers. Continue independent repository inspection while awaiting them.
3. Write a minimal AGENTS.md: one short actionable line per essential constraint,
   canonical commands, and links to detailed docs. Aim for under 60 lines, remove
   unused sections and omit rules already enforced by formatting/linting. Do not
   paste this skill, long explanations or generic style advice into AGENTS.md.
4. Convert each deterministic invariant into a meaningful offline test. Isolate
   config and dotenv before imports, block networking, and mock external seams.
   Demonstrate each new guard fails for a temporary violation, then restore code.
   Use strict xfail only for confirmed unfixed bugs asserting correct behavior.
   Never weaken tests or regenerate an accepted golden to get a pass.
5. Derive the review skill's numbered rules directly from AGENTS.md. Cite the
   source invariant, specific violating evidence and legitimate exceptions. Put
   only rules requiring judgment here; don't duplicate computational checks.
   If no such rules exist, state that explicitly instead of inventing rules.
6. Add owner-approved violating and clean patch cases for the reviewer, with
   neutral filenames at model invocation (the runner handles this). Ground-truth
   labels remain owner-controlled; never change them to improve scores.
7. Run scripts/check.sh and pre-commit; report the mapping from each invariant to
   test or review rule and any uncovered requirement. Propose golden/evals/plans
   only when project behavior warrants them. Keep AGENTS.md minimal on every edit.
