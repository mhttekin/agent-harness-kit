"""The PreToolUse guard blocks chained git commit/push/switch that would not stop on a failed step."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.bash_guard import problem

ROOT = Path(__file__).resolve().parents[1]

# The two commands that went wrong in an adopted project, as they were run.
SWITCH_THEN_RENDER = """sed -i '' 's/^agents: .*/agents: [claude, codex]/' answers.yml && cat answers.yml
cd ~/projects/app && [ -z "$(git status --porcelain)" ] && echo CLEAN || { echo DIRTY; exit 1; }
git switch -c harness
copier copy --defaults --data-file answers.yml ~/projects/kit .
git status --short"""

TWO_COMMITS = """cd ~/projects/app && git add a.sh b.py && git commit -q -F - <<'EOF'
Update the harness

- a.sh; b.py
EOF
git add README.md && git commit -q -F - <<'EOF'
Docs for the update
EOF
git log --oneline -3"""

FAIL_FAST = """cd ~/projects/app && bash -euo pipefail <<'SCRIPT'
git add a.sh b.py
git commit -q -F - <<'EOF'
Update the harness
EOF
git add README.md
git commit -q -F - <<'EOF'
Docs for the update
EOF
SCRIPT
git status --short; git log --oneline -3"""


@pytest.mark.parametrize(
    "command",
    [
        SWITCH_THEN_RENDER,
        TWO_COMMITS,
        "git add . ; git commit -m x",
        "cd repo; git push origin feature",
        "git commit -m x & git push",
        "make test\ngit -C repo commit -am wip",
        "git commit -m a; set -e; git push",
        "set -e; set +e; git add a; git commit -m x",
        "bash <<'S'\ngit add a\ngit commit -m x\nS",
        "for f in a b; do git add $f; done; git commit -m x",
    ],
)
def test_blocks_steps_that_would_run_after_a_failure(command):
    assert problem(command)


@pytest.mark.parametrize(
    "command",
    [
        FAIL_FAST,
        "git commit -m x",
        "git add a && git commit -m 'a; b' && git push",
        'git commit -m "first; second\nthird"',
        "git commit -q -F - <<'EOF'\nline one\nline two; still the message\nEOF",
        "set -euo pipefail\ngit add a\ngit commit -m x\ngit push",
        "set -o errexit; git commit -m x; git push",
        "git status; git log --oneline -3",
        'echo "git commit; git push"; date',
        "# git commit; git push\ngit status",
        "git commit \\\n  -m x \\\n  -q",
        "git -C repo commit -m x && git -C repo push 2>&1 | tail -1",
        "x=$(git commit -m a; echo done) && echo $x",
        "git switch main || git switch -c main",
        "zsh -e <<'S'\ngit add a\ngit commit -m x\nS",
    ],
)
def test_allows_single_steps_chains_and_errexit(command):
    assert problem(command) is None


def run_hook(payload):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/bash_guard.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def test_the_hook_blocks_with_exit_2_and_a_reason():
    done = run_hook({"tool_name": "Bash", "tool_input": {"command": TWO_COMMITS}})
    assert done.returncode == 2
    assert "set -euo pipefail" in done.stderr
    assert done.stdout == ""


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}},
        {"tool_name": "Write", "tool_input": {"content": TWO_COMMITS}},
        {"tool_name": "Bash", "tool_input": {}},
    ],
)
def test_the_hook_lets_everything_else_through(payload):
    done = run_hook(payload)
    assert done.returncode == 0
    assert done.stderr == ""


def test_both_agents_run_the_guard_before_bash():
    claude = ROOT / ".claude/settings.json"
    codex = ROOT / ".codex/config.toml"
    if claude.exists():
        groups = json.loads(claude.read_text())["hooks"]["PreToolUse"]
        commands = [h["command"] for g in groups if g["matcher"] == "Bash" for h in g["hooks"]]
        assert any("agent-hooks/pre-bash.sh" in c for c in commands)
    if codex.exists():
        text = codex.read_text()
        assert '[[hooks.PreToolUse]]\nmatcher = "^Bash$"' in text
        assert "agent-hooks/pre-bash.sh" in text.split("[[hooks.PreToolUse]]", 1)[1]
