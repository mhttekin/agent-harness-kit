"""Exercise loop ownership and failure preservation without launching paid agents."""

import argparse
import json
import subprocess
from contextlib import nullcontext
from pathlib import Path

import pytest

from scripts import run_units as loop


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for args in (
        ("init", "-b", "main"),
        ("config", "user.name", "Harness Test"),
        ("config", "user.email", "test@example.invalid"),
        ("config", "commit.gpgsign", "false"),
        ("config", "core.hooksPath", "/dev/null"),
    ):
        subprocess.run(["git", *args], check=True, capture_output=True)
    plan = Path("docs/plans/example")
    plan.mkdir(parents=True)
    (plan / "features.schema.json").write_text(json.dumps({"type": "array"}))
    units = [{"id": "one", "description": "Change sample", "paths": ["sample.py"], "passes": False}]
    (plan / "features.json").write_text(json.dumps(units))
    (plan / "progress.md").write_text("# Progress\n")
    (plan / "init.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    (plan / "init.sh").chmod(0o755)
    Path("scripts").mkdir()
    Path("scripts/check.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    Path("scripts/check.sh").chmod(0o755)
    Path(".gitignore").write_text(".agent-logs/\n")
    Path("sample.py").write_text("value = 1\n")
    Path("evals/labels").mkdir(parents=True)
    Path("evals/labels/sample.json").write_text("{}")
    Path("Tests/Demo/__Snapshots__").mkdir(parents=True)
    Path("Tests/Demo/__Snapshots__/sample.txt").write_text("accepted")
    paths = [str(p) for p in Path(".").rglob("*") if p.is_file() and ".git" not in p.parts]
    subprocess.run(["git", "add", "--", *paths], check=True)
    subprocess.run(["git", "commit", "-m", "Baseline"], check=True, capture_output=True)
    monkeypatch.setattr(loop, "agent_environment", lambda agent: nullcontext({}))
    monkeypatch.setattr(loop, "command", lambda *args: ["fake-agent"])
    monkeypatch.setattr(loop, "review", lambda *args: {"error": False, "text": "VERDICT: PASS"})
    return argparse.Namespace(
        plan=str(plan), agent="codex", max_units=1, timeout_min=1, dry_run=False
    )


def edit(*args, **kwargs):
    Path("sample.py").write_text("value = 2\n")
    return 0


def test_loop_commits_only_after_verification(checkout, monkeypatch):
    monkeypatch.setattr(loop, "wait", edit)
    assert loop.run(checkout) == 0
    assert loop.git("rev-list", "--count", "HEAD") == "2"
    assert json.loads(Path(checkout.plan, "features.json").read_text())[0]["passes"] is True
    assert loop.git("status", "--porcelain") == ""


@pytest.mark.parametrize(
    "failure", ["labels", "snapshots", "queue", "scope", "staged", "review", "mutation"]
)
def test_failure_preserves_changes_without_commit(checkout, monkeypatch, failure):
    def child(*args, **kwargs):
        edit()
        if failure == "labels":
            Path("evals/labels/sample.json").write_text('{"changed":true}')
        if failure == "snapshots":
            Path("Tests/Demo/__Snapshots__/sample.txt").write_text("changed")
        if failure == "queue":
            Path(checkout.plan, "features.json").write_text("[]")
        if failure == "scope":
            Path("outside.py").write_text("value = 3\n")
        if failure == "staged":
            subprocess.run(["git", "add", "--", "sample.py"], check=True)
        return 0

    def reviewer(*args):
        if failure == "mutation":
            Path("sample.py").write_text("value = 99\n")
        return {"error": False, "text": "VERDICT: FAIL" if failure == "review" else "VERDICT: PASS"}

    monkeypatch.setattr(loop, "wait", child)
    monkeypatch.setattr(loop, "review", reviewer)
    with pytest.raises(RuntimeError):
        loop.run(checkout)
    assert loop.git("rev-list", "--count", "HEAD") == "1"
    assert Path("sample.py").read_text() != "value = 1\n"


def test_dry_run_does_not_launch_child(checkout, monkeypatch):
    checkout.dry_run = True
    monkeypatch.setattr(loop, "wait", lambda *args, **kwargs: pytest.fail("Agent launched"))
    assert loop.run(checkout) == 0
    assert loop.git("status", "--porcelain") == ""
