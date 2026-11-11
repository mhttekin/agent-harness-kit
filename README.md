# Agent Harness Kit

Requires Python 3.11 or newer.

Reusable Copier template for Python and Swift repositories' agent harness. No product rules,
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

Questions: project name, package identifier, language (Python or Swift),
lint and test shell commands, and enabled agents (Claude/Codex, either, both or none).
Commands are trusted user input and run inside check.sh. Language-specific
rendering branches cover package/config/gate/test files; all agent launchers,
hook adapters, docs, review and eval infrastructure, and loop code are shared.
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
- Chain multi-step shell commands with `&&` or `set -e`; a failed step must stop the
  sequence. An agent once kept going after `git switch -c` failed and ran Copier on `main`.

These are generalized lessons extracted from harness progress logs and decision
records, domain-specific experiments and rules deliberately remain in their source.

## Maintainer verification

Run `./scripts/check.sh` in this template repository. It renders a fresh sample
using the Copier CLI, installs it in an isolated venv, and runs its gate, pre-commit
and pre-push checks. It also renders Claude-only, Codex-only, and no-agent variants. On macOS it
verifies a SwiftPM sample and renders Xcode project/workspace variants. Install
SwiftLint first (`brew install swiftlint`); swift-format comes with Xcode.
First installation may need package-index access. No paid model sessions run.
Copier configuration reference: https://copier.readthedocs.io/en/stable/configuring/

## Swift

```sh
copier copy --vcs-ref=v0.2.0 -d language=swift \
  https://github.com/mhttekin/agent-harness-kit.git /tmp/swift-harness
```

Install Copier separately if the command is missing, or use `.venv/bin/copier`
from this kit after installing requirements-dev.txt. The Swift application uses
SwiftPM by default; shared harness scripts still need a Python 3.11+ venv.
Swift questions select SwiftPM or Xcode, an exact CI Xcode version (default 26.3),
and for Xcode the existing project/workspace, shared scheme and destination.
Scheme and destination values are stored as JSON, never evaluated as shell code.
Xcode mode emits adoption examples, not an invented .xcodeproj; integrate those
with your existing targets and SnapshotTesting dependency. Python's commands,
sample and CI matrix retain their existing behavior.

The gate checks swift-format and SwiftLint, builds, runs tests, and applies the
shared shell size ratchet. Swift examples demonstrate strict known issues,
non-recording snapshot goldens and injected URLSession network blocking. The
URLProtocol stub is not a socket firewall and does not guard URLSession.shared.
Package resolution downloads dependencies; the tests themselves use fixtures.

Swift pitfalls: DerivedData, compiler caches and simulator services may require
narrow access outside an agent sandbox. Resolve packages before restricted agent
sessions; never disable sandboxing to fix access failures. Match Xcode and
simulator versions for image goldens. macOS CI costs more than Linux; use the
provided timeout and deliberately scope expensive UI/device suites.

The pinned [Xcode 26.3 on macos-15](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-Readme.md)
is a CI selection; the sample requires Swift 6.0 or newer locally. Format output
can differ by Xcode version, so recheck it when changing the toolchain pin.

The language-neutral size gate reads `.harness/ratchets.tsv` (limit<TAB>path).
Add source paths explicitly and lower their caps as files shrink. No production
project was modified while developing or verifying these examples.
