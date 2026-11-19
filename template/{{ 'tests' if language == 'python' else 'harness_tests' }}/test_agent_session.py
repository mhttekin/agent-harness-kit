"""Interactive sessions may write .git; loop runs may not; every launch checks the CLI login."""

import json
import os
import stat

import pytest

from scripts import agent_session as session


def enabled(agent):
    return pytest.mark.skipif(agent not in session.ENABLED, reason=f"{agent} is not enabled")


@pytest.fixture
def gitdir(monkeypatch):
    monkeypatch.setattr(session, "git_dir", lambda: "/repo/.git")
    return "/repo/.git"


def claude_settings(cmd):
    return json.loads(cmd[cmd.index("--settings") + 1])


@enabled("claude")
def test_loop_claude_keeps_git_read_only_and_offline(gitdir):
    settings = claude_settings(session.command("claude", [], "brief"))
    assert settings["sandbox"]["filesystem"]["denyWrite"] == [gitdir]
    assert settings["sandbox"]["network"]["allowedDomains"] == []
    assert "permissions" not in settings


@enabled("claude")
def test_interactive_claude_can_commit_and_push_a_branch(gitdir):
    settings = claude_settings(session.command("claude", []))
    assert gitdir not in json.dumps(settings["sandbox"]["filesystem"])
    assert settings["sandbox"]["network"]["allowedDomains"] == ["github.com"]
    deny = settings["permissions"]["deny"]
    for rule in (
        "Bash(git push * main)",
        "Bash(git push *:main)",
        "Bash(git push --force*)",
        "Bash(git commit --no-verify*)",
    ):
        assert rule in deny
    # After a "*", Claude Code reads ":*" as a literal prefix that never matches.
    assert not any(rule.endswith(":*)") and "* " in rule for rule in deny)


@enabled("codex")
def test_loop_codex_keeps_git_read_only(gitdir):
    cmd = session.command("codex", [], "brief")
    assert "exec" in cmd
    assert not any("writable_roots" in part for part in cmd)


@enabled("codex")
def test_interactive_codex_makes_only_git_writable(gitdir):
    cmd = session.command("codex", ["--version"])
    assert f'sandbox_workspace_write.writable_roots=["{gitdir}"]' in cmd
    assert "sandbox_workspace_write.network_access=false" in cmd
    assert cmd[-1] == "--version"


def fake_cli(tmp_path, name, code, stdout=""):
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\nprintf '%s' '{stdout}'\nexit {code}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}


@pytest.mark.parametrize(
    ("agent", "code", "stdout", "ok"),
    [
        ("claude", 0, '{"loggedIn": true}', True),
        ("claude", 1, '{"loggedIn": false}', False),
        ("claude", 0, '{"loggedIn": false}', False),
        ("claude", 0, "not json", False),
        ("codex", 0, "Logged in using ChatGPT", True),
        ("codex", 1, "Not logged in", False),
    ],
)
def test_the_launcher_stops_when_not_logged_in(tmp_path, agent, code, stdout, ok):
    env = fake_cli(tmp_path, agent, code, stdout)
    if ok:
        session.require_login(agent, env)
    else:
        with pytest.raises(SystemExit, match="not logged in"):
            session.require_login(agent, env)


def test_a_missing_cli_stops_the_launch(tmp_path):
    with pytest.raises(SystemExit, match="could not check"):
        session.require_login("codex", {"PATH": str(tmp_path)})
