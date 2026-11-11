# Agent Harness Kit

Requires Python 3.11 or newer.

Reusable Copier template for a Python repository's agent harness. No product rules,
labels, credentials or historical plans are included.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/copier copy . /tmp/my-project
cd /tmp/my-project
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
git init
./scripts/check.sh
```

Questions: project name, Python package identifier, language (currently Python),
lint and test shell commands, and enabled agents (Claude/Codex, either, both or none).
Commands are trusted user input and run inside check.sh. Language-specific
rendering branches live in the Python templates; add a language choice and its
package/config/gate/test renderers together. Python is the only supported choice.
No Copier tasks execute automatically. `.copier-answers.yml` supports later updates.

For an existing project, generate into a scratch checkout, merge harness files,
and keep the existing package/build configuration; do not overwrite it blindly.
Run `.agents/skills/harness-bootstrap/SKILL.md` to interview the owner, write a
minimal local AGENTS.md and derive tests and review rules from those invariants.

Adoption order: **AGENTS.md → gates → hooks → invariant tests → golden → evals →
reviewer → plans/loop**. The generated README describes each entry point and loop
ownership. Stop at the layer your project needs; reviewer/model evals cost usage
and are excluded from the offline gate.

## Pitfalls checklist

- Codex Stop: emit JSON only, capture check output, and honor stop_hook_active to
  prevent endless automatic retries. A repeated-failure warning is not a green gate.
- Restart sessions after hook changes so configuration is reloaded.
- Nested sandboxes can break shell/test launches: preflight actual commands in the
  deployment environment; keep sandbox restrictions enabled.
- tmux preserves its server environment: refresh intended variables and confirm
  CLI authentication inside the pane without logging secrets.
- Tests must opt out of dotenv before imports and redirect config to temporary
  paths; pytest-socket prevents networking, not local secret reads.
- The loop owns Git; children must not stage, commit, reset, push or stash.
  Failures stop with changes preserved for operator inspection.
- Protect accepted goldens, test that meaningful mutations fail, and control clocks
  and ordering. Do not recapture goldens just to make changes pass.
- ADRs need metrics, limitations and revisit conditions. Re-read rejected approaches
  before retrying; sparse labels do not prove general improvements. Compare every
  metric rather than assuming an eval command's success implies no regression.

These are generalized lessons extracted from harness progress logs and decision
records; domain-specific experiments and rules deliberately remain in their source.

## Maintainer verification

Run `./scripts/check.sh` in this template repository. It renders a fresh sample
using the Copier CLI, installs it in an isolated venv, and runs its gate, pre-commit
and pre-push checks. It also renders Claude-only, Codex-only, and no-agent variants.
First installation may need package-index access. No paid model sessions run.
Copier configuration reference: https://copier.readthedocs.io/en/stable/configuring/
