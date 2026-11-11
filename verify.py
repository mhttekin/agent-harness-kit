"""Render actual Copier CLI outputs and exercise the offline harness."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent


def call(*args, cwd=None, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


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
        probe = sample / "src/tiny_sample/__init__.py"
        original = probe.read_text()
        try:
            probe.write_text(original + "\nFORMAT_PROBE= 1\n")
            failure = subprocess.run(
                ["./scripts/check.sh"], cwd=sample, capture_output=True
            )
            assert failure.returncode != 0, (
                "Formatting failure was swallowed by the gate"
            )
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
        print(
            "PASS: Copier variants, sample checks, both hook stages, label protection."
        )


if __name__ == "__main__":
    main()
