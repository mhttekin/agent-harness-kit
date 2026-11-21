"""Render actual Copier CLI outputs and exercise the offline harness."""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent


def call(*args, cwd=None, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def render_swift(dest, **answers):
    argv = [
        sys.executable,
        "-m",
        "copier",
        "copy",
        "--defaults",
        "--vcs-ref=HEAD",
        "--quiet",
        "-d",
        "project_name=Tiny Sample",
        "-d",
        "package_name=tiny_swift",
        "-d",
        "language=swift",
    ]
    for key, value in answers.items():
        argv.extend(["-d", f"{key}={value}"])
    call(*argv, str(ROOT), str(dest))


def git_commit(cwd, message):
    call(
        "git",
        "-c",
        "user.name=verify",
        "-c",
        "user.email=verify@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
        cwd=cwd,
    )


def fails(*args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True).returncode != 0


def assert_ci_has_no_blank_lines(sample):
    text = (sample / ".github/workflows/ci.yml").read_text()
    lines = text.split("\n")
    assert text.endswith("\n") and not text.endswith("\n\n"), f"{sample.name}: ci.yml ending"
    assert all(line.strip() for line in lines[:-1]), f"{sample.name}: blank lines in ci.yml"


def assert_suite_leaves_git_alone(scratch, sample, python, tests_dir):
    """A pre-commit or pre-push hook runs the suite with GIT_DIR exported: it must not touch that repository."""
    target = scratch / f"git-target-{sample.name}"
    target.mkdir()
    call("git", "init", "-q", "-b", "main", cwd=target)
    (target / "file.txt").write_text("x\n")
    call("git", "add", "file.txt", cwd=target)
    git_commit(target, "target")

    def state():
        refs = subprocess.check_output(
            ["git", "for-each-ref", "--format=%(refname) %(objectname)"], cwd=target, text=True
        )
        git_dir = target / ".git"
        return (git_dir / "config").read_bytes(), refs, (git_dir / "HEAD").read_text()

    before = state()
    env = dict(os.environ, GIT_DIR=str(target / ".git"), GIT_INDEX_FILE=str(target / ".git/index"))
    call(python, "-m", "pytest", "-q", "-p", "no:cacheprovider", tests_dir, cwd=sample, env=env)
    assert state() == before, f"{sample.name}: the test suite changed the repository GIT_DIR points at"


def verify_swift_existing(scratch, venv):
    """Existing-code mode: format only changed files, SwiftLint against a portable baseline."""
    sample = scratch / "swiftpm-existing"
    render_swift(sample, swift_adoption="existing")
    for relative in (
        "scripts/standard-root.sh",
        "harness_tests/test_lint_paths.py",
        "docs/decisions/0001-gate-new-format-and-lint-only.md",
    ):
        assert (sample / relative).exists(), relative
    assert "fetch-depth: 0" in (sample / ".github/workflows/ci.yml").read_text()
    assert_ci_has_no_blank_lines(sample)
    legacy = sample / "Sources/tiny_swift/Legacy.swift"
    legacy.write_text(
        "import Foundation\n\npublic func legacy() -> Data {\n  try! JSONEncoder().encode([1])\n}\n"
    )
    call("git", "init", "-q", "-b", "main", cwd=sample)
    call("git", "add", "-A", cwd=sample)
    git_commit(sample, "adopt")
    call("git", "switch", "-q", "-c", "feature", cwd=sample)
    quality = "./scripts/swift-quality.sh"
    assert fails(quality, "lint", cwd=sample), "Lint passed without a baseline"
    call(quality, "write-baseline", cwd=sample)
    entries = json.loads((sample / ".harness/swiftlint-baseline.json").read_text())
    assert [e["violation"]["location"]["file"] for e in entries] == [
        "Sources/tiny_swift/Legacy.swift"
    ]
    call(quality, "all", cwd=sample)
    call("git", "add", "-A", cwd=sample)
    git_commit(sample, "baseline")
    clone = scratch / "swiftpm-existing-clone"
    call("git", "clone", "-q", "--branch", "feature", str(sample), str(clone))
    call(quality, "lint", cwd=clone)  # the baseline matches in another checkout
    fresh = sample / "Sources/tiny_swift/Fresh.swift"
    fresh.write_text(
        "import Foundation\n\npublic func fresh() -> Data {\n  try! JSONEncoder().encode([2])\n}\n"
    )
    assert fails(quality, "lint", cwd=sample), "A new SwiftLint violation passed"
    call(quality, "format", cwd=sample)
    fresh.write_text("public func fresh() {\n      let x =  1\n  _ = x\n}\n")
    assert fails(quality, "format", cwd=sample), "A badly formatted changed file passed"
    call("./scripts/fix-file.sh", str(fresh), cwd=sample)
    call(quality, "all", cwd=sample)
    fresh.unlink()
    env = dict(os.environ, HARNESS_BASE_REF="no-such-ref")
    assert fails(quality, "format", cwd=sample, env=env), "A missing base passed as no changes"
    call("git", "switch", "-q", "main", cwd=sample)
    call("git", "merge", "-q", "feature", cwd=sample)
    (sample / "Sources/tiny_swift/Direct.swift").write_text(
        "public func direct() {\n      let x =  1\n}\n"
    )
    call("git", "add", "-A", cwd=sample)
    git_commit(sample, "direct")
    assert fails(quality, "format", cwd=sample), "A direct commit on main skipped the format check"
    call(str(venv / "bin/python"), "-m", "pytest", "-q", "harness_tests", cwd=sample)
    assert_suite_leaves_git_alone(scratch, sample, str(venv / "bin/python"), "harness_tests")
    clt = Path("/Library/Developer/CommandLineTools")
    if clt.is_dir():
        call(quality, "lint", cwd=clone, env=dict(os.environ, DEVELOPER_DIR=str(clt)))
    print(
        "PASS: existing-code mode: changed-file format, portable SwiftLint baseline, main checks."
    )


def verify_swift(scratch, python_sample):
    sample = scratch / "swiftpm"
    render_swift(sample)
    assert (sample / "Package.swift").exists()
    assert not (sample / "pyproject.toml").exists()
    assert not (sample / "src").exists()
    shared = [
        "AGENTS.md",
        "scripts/agent.sh",
        "scripts/agent_session.py",
        "scripts/agent-hooks/post-edit.sh",
        "scripts/agent-hooks/pre-bash.sh",
        "scripts/bash_guard.py",
        "scripts/codex_stop.py",
        "scripts/run_units.py",
        "scripts/ratchet.sh",
        ".agents/skills/review/SKILL.md",
        ".agents/skills/harness-bootstrap/SKILL.md",
        "docs/plans/template/plan.md",
        "evals/README.md",
    ]
    for relative in shared:
        assert (sample / relative).read_bytes() == (python_sample / relative).read_bytes(), relative
    call(sys.executable, "-m", "venv", str(sample / ".venv"))
    python = str(sample / ".venv/bin/python")
    call(python, "-m", "pip", "install", "-r", "requirements-harness.txt", cwd=sample)
    call("git", "init", "-b", "main", cwd=sample)
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=sample, text=True
        )
        .strip("\0")
        .split("\0")
    )
    call("git", "add", "--", *paths, cwd=sample)
    call("./scripts/check.sh", cwd=sample)
    call(python, "-m", "pytest", "-q", "harness_tests", cwd=sample)
    assert_suite_leaves_git_alone(scratch, sample, python, "harness_tests")
    assert_ci_has_no_blank_lines(sample)
    env = dict(os.environ, ALLOW_LABEL_EDIT="1", PRE_COMMIT_HOME=str(scratch / "swift-pre-commit"))
    for stage in ("pre-commit", "pre-push"):
        call(
            str(sample / ".venv/bin/pre-commit"),
            "run",
            "--all-files",
            "--hook-stage",
            stage,
            cwd=sample,
            env=env,
        )
    source = sample / "Sources/tiny_swift/HarnessSample.swift"
    original = source.read_text()
    snapshot = (
        sample / "Tests/tiny_swiftTests/__Snapshots__/HarnessSampleTests/describe.baseline.txt"
    )
    golden = snapshot.read_bytes()
    try:
        source.write_text(original + "\nlet formatProbe =  1\n")
        failed = subprocess.run(["./scripts/check.sh"], cwd=sample, capture_output=True)
        assert failed.returncode != 0, "Swift format failure did not block"
        call("./scripts/fix-file.sh", str(source), cwd=sample)
        call("./scripts/swift-quality.sh", "format", cwd=sample)
        source.write_text(original + "\n" * 401)
        failed = subprocess.run(["./scripts/ratchet.sh"], cwd=sample, capture_output=True)
        assert failed.returncode != 0, "Ratchet failed to reject oversized source"
        source.write_text(original.replace('"name=', '"changed-name='))
        failed = subprocess.run(
            ["swift", "test", "--filter", "descriptionMatchesGolden"],
            cwd=sample,
            capture_output=True,
        )
        assert failed.returncode != 0, "Golden did not catch behavior change"
        assert snapshot.read_bytes() == golden, "Golden was rewritten"
        source.write_text(original.replace("name.unicodeScalars.count", "name.count"))
        failed = subprocess.run(
            ["swift", "test", "--filter", "knownIssueIsStrict"], cwd=sample, capture_output=True
        )
        assert failed.returncode != 0, "Known issue accepted an unexpected pass"
    finally:
        source.write_text(original)
    call("./scripts/check.sh", cwd=sample)
    hook = (sample / "scripts/fix-file.sh").read_text().splitlines()
    assert not [line for line in hook if line.startswith("swiftlint") and "--fix" in line]
    assert not (sample / "scripts/standard-root.sh").exists()
    assert not (sample / "docs/decisions/0001-gate-new-format-and-lint-only.md").exists()
    verify_swift_existing(scratch, sample / ".venv")
    # Resolve dependencies before staging them in a real adopted project.
    assert (sample / "Package.resolved").exists()
    for kind in ("project", "workspace"):
        xcode = scratch / f"xcode-{kind}"
        render_swift(
            xcode,
            swift_build_system="xcode",
            xcode_container_kind=kind,
            xcode_container=f"App With Spaces.xc{'workspace' if kind == 'workspace' else 'odeproj'}",
            xcode_scheme="App Tests",
            xcode_destination="platform=iOS Simulator,name=iPhone 17,OS=26.2",
        )
        assert not (xcode / "Package.swift").exists()
        assert (xcode / "examples/swift/Tests/tiny_swiftTests/NetworkStub.swift").exists()
        for relative in shared:
            assert (xcode / relative).read_bytes() == (sample / relative).read_bytes(), relative
        probe = (
            "import json,runpy,subprocess; commands=[]; "
            "subprocess.run=lambda args,**kw: commands.append(args); "
            "runpy.run_path('scripts/xcode_check.py'); print(json.dumps(commands))"
        )
        commands = json.loads(subprocess.check_output([python, "-c", probe], cwd=xcode, text=True))
        assert [cmd[-1] for cmd in commands] == ["build", "test"]
        assert commands[0][1] == "-" + kind
        assert commands[0][commands[0].index("-scheme") + 1] == "App Tests"
        assert (
            commands[0][commands[0].index("-destination") + 1]
            == "platform=iOS Simulator,name=iPhone 17,OS=26.2"
        )
    print(
        "PASS: SwiftPM gate, hook stages, strict known issue, golden, network stub, ratchet and Xcode argv."
    )


def main():
    if sys.version_info < (3, 11):
        sys.exit("Verification requires Python 3.11 or newer")
    with TemporaryDirectory(prefix="harness-verify-") as directory:
        scratch = Path(directory)
        sample = scratch / "sample"
        call(
            sys.executable,
            "-m",
            "copier",
            "copy",
            "--defaults",
            "--vcs-ref=HEAD",
            "-d",
            "project_name=Tiny Sample",
            "-d",
            "package_name=tiny_sample",
            str(ROOT),
            str(sample),
        )
        for agents in (["claude"], ["codex"], []):
            dest = scratch / ("-".join(agents) or "no-agents")
            call(
                sys.executable,
                "-m",
                "copier",
                "copy",
                "--defaults",
                "--vcs-ref=HEAD",
                "-d",
                f"agents_enabled={json.dumps(agents)}",
                str(ROOT),
                str(dest),
            )
            assert (dest / ".claude").exists() == ("claude" in agents)
            assert (dest / "CLAUDE.md").exists() == ("claude" in agents)
            assert (dest / ".codex").exists() == ("codex" in agents)
        call(sys.executable, "-m", "venv", str(sample / ".venv"))
        python = str(sample / ".venv/bin/python")
        call(python, "-m", "pip", "install", "-e", ".[dev]", cwd=sample)
        call("git", "init", "-b", "main", cwd=sample)
        paths = (
            subprocess.check_output(
                ["git", "ls-files", "--others", "--exclude-standard", "-z"],
                cwd=sample,
                text=True,
            )
            .strip("\0")
            .split("\0")
        )
        call("git", "add", "--", *paths, cwd=sample)
        call("./scripts/check.sh", cwd=sample)
        assert_suite_leaves_git_alone(scratch, sample, python, "tests")
        assert_ci_has_no_blank_lines(sample)
        probe = sample / "src/tiny_sample/__init__.py"
        original = probe.read_text()
        try:
            probe.write_text(original + "\nFORMAT_PROBE= 1\n")
            failure = subprocess.run(["./scripts/check.sh"], cwd=sample, capture_output=True)
            assert failure.returncode != 0, "Formatting failure was swallowed by the gate"
        finally:
            probe.write_text(original)
        # Initial scaffold labels are deliberately owner-authorized for adoption.
        env = dict(
            os.environ,
            ALLOW_LABEL_EDIT="1",
            PRE_COMMIT_HOME=str(scratch / "pre-commit"),
        )
        call(
            str(sample / ".venv/bin/pre-commit"),
            "run",
            "--all-files",
            cwd=sample,
            env=env,
        )
        call(
            str(sample / ".venv/bin/pre-commit"),
            "run",
            "--all-files",
            "--hook-stage",
            "pre-push",
            cwd=sample,
            env=env,
        )
        denied = subprocess.run(
            [python, "scripts/protect_labels.py"],
            cwd=sample,
            env={k: v for k, v in env.items() if k != "ALLOW_LABEL_EDIT"},
        )
        assert denied.returncode != 0
        call(python, "-m", "compileall", "-q", "scripts", "evals", cwd=sample)
        call(
            python,
            "-m",
            "json.tool",
            "docs/plans/template/features.schema.json",
            str(scratch / "schema.json"),
            cwd=sample,
        )
        if platform.system() == "Darwin":
            verify_swift(scratch, sample)
        else:
            print("Swift execution requires macOS; Python verification completed.")
        print("PASS: Copier variants, sample checks, both hook stages, label protection.")


if __name__ == "__main__":
    main()
