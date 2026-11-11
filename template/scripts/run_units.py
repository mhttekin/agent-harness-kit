"""Generic ordered unit loop. Stops on failure, preserving the checkout for inspection."""

import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import ValidationError, validate

from scripts.agent_session import ENABLED, agent_environment, command, wait
from scripts.reviewer_agent import run as review


def git(*args):
    return subprocess.check_output(["git", *args], text=True).rstrip("\n")


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def changes():
    raw = git("status", "--porcelain", "-z", "--no-renames", "--untracked-files=all")
    entries = [entry for entry in raw.split("\0") if entry]
    require(
        all(entry[:2] in (" M", " D", "??") for entry in entries),
        "Child must leave changes unstaged",
    )
    return [entry[3:] for entry in entries]


def contents(paths):
    return {
        path: hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None
        for path in paths
    }


def protected():
    files = list(Path("evals/labels").rglob("*")) + list(Path("tests/fixtures").rglob("*"))
    snapshots = git(
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        ":(glob)**/__Snapshots__/**",
    )
    files.extend(Path(path) for path in snapshots.split("\0") if path)
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.is_file()
    }


def run(args):
    plan = Path(args.plan).resolve()
    root = Path.cwd().resolve()
    require(plan.is_relative_to(root), "Plan must be inside this checkout")
    queue_path = plan / "features.json"
    schema = json.loads((plan / "features.schema.json").read_text())
    for _ in range(args.max_units):
        require(not git("status", "--porcelain"), "Start with a clean committed checkout")
        head = git("rev-parse", "HEAD")
        units = json.loads(queue_path.read_text())
        validate(units, schema)
        ids = [unit["id"] for unit in units]
        require(len(set(ids)) == len(ids), "Duplicate unit IDs")
        for entry in units:
            require(
                all(
                    dep in ids and ids.index(dep) < ids.index(entry["id"])
                    for dep in entry.get("requires", [])
                ),
                "Dependencies must precede units",
            )
        unit = next((item for item in units if not item["passes"]), None)
        if unit is None:
            print("No pending units.")
            return 0
        done = {item["id"] for item in units if item["passes"]}
        require(set(unit.get("requires", [])) <= done, "Unmet unit dependency")
        for path in unit["paths"]:
            require(
                not path.startswith(("-", ":")) and (root / path).resolve().is_relative_to(root),
                "Invalid unit path",
            )
        if args.dry_run:
            print(json.dumps(unit, indent=2))
            return 0
        subprocess.run([str(plan / "init.sh")], check=True)
        require(not git("status", "--porcelain"), "Initializer changed checkout")
        require(git("rev-parse", "HEAD") == head, "Initializer changed HEAD")
        baseline = protected()
        log = Path(".agent-logs") / f"{unit['id']}-{head[:8]}"
        require(not log.exists(), f"Log exists; inspect before retrying: {log}")
        log.mkdir(parents=True)
        brief = (
            f"Read AGENTS.md and {plan.relative_to(root)}/plan.md and progress.md. "
            f"Do ONLY this unit: {json.dumps(unit)}. "
            "Run the gates; append evidence to progress.md. Leave all changes unstaged "
            "and uncommitted. Do not modify features.json. The loop owns Git. "
            "Never change accepted goldens or labels."
        )
        (log / "brief.md").write_text(brief)
        with (
            agent_environment(args.agent) as env,
            (log / "stdout.jsonl").open("w") as out,
            (log / "stderr.log").open("w") as err,
        ):
            status = wait(
                command(args.agent, [], brief),
                env,
                args.timeout_min * 60,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
            )
        require(status == 0, f"Agent failed: {status}; inspect {log}")
        require(git("rev-parse", "HEAD") == head, "Child changed HEAD")
        require(json.loads(queue_path.read_text()) == units, "Child changed queue")
        require(protected() == baseline, "Protected labels/goldens changed")
        paths = changes()
        allowed = [*unit["paths"], str(plan.relative_to(root) / "progress.md")]
        require(
            paths
            and all(
                any(
                    path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")
                    for prefix in allowed
                )
                for path in paths
            ),
            f"Changes outside unit scope: {paths}",
        )
        subprocess.run(["./scripts/check.sh"], check=True)
        require(protected() == baseline, "Checks changed protected files")
        require(changes() == paths, "Checks changed file set")
        patch = git("diff", "--no-ext-diff", "--no-color", "HEAD") + "\n"
        for path in paths:
            if not git("ls-files", "--", path):
                diff = subprocess.run(
                    ["git", "diff", "--no-index", "--", "/dev/null", path],
                    capture_output=True,
                    text=True,
                )
                require(diff.returncode in (0, 1), "Cannot capture new file diff")
                patch += diff.stdout
        reviewed_contents = contents(paths)
        patch_path = log / "change.patch"
        patch_path.write_text(patch)
        result = review(
            args.agent,
            f"Follow .agents/skills/review/SKILL.md to review {patch_path}. "
            "Read only; do not modify anything. This is fresh context.",
            root,
            args.timeout_min * 60,
        )
        (log / "review.txt").write_text(result["text"])
        require(
            not result["error"] and result["text"].strip().endswith("VERDICT: PASS"),
            f"Review did not pass; inspect {log}",
        )
        require(
            git("rev-parse", "HEAD") == head and changes() == paths,
            "Checkout changed during review",
        )
        require(
            contents(paths) == reviewed_contents and protected() == baseline,
            "File contents changed during review",
        )
        require(json.loads(queue_path.read_text()) == units, "Reviewer changed queue")
        # Only the loop changes completion state after gates and independent review.
        unit["passes"] = True
        queue_path.write_text(json.dumps(units, indent=2) + "\n")
        paths.append(str(queue_path.relative_to(root)))
        subprocess.run(["git", "--literal-pathspecs", "add", "--", *paths], check=True)
        subprocess.run(["git", "commit", "-m", f"Complete unit: {unit['id']}"], check=True)
        require(git("show", "-s", "--format=%P", "HEAD") == head, "Expected one commit")
        require(not git("status", "--porcelain"), "Checkout dirty after commit")
        print(f"Completed {unit['id']}; local commit only.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default="docs/plans/template")
    parser.add_argument("--agent", choices=ENABLED, required=True)
    parser.add_argument("--max-units", type=int, default=1)
    parser.add_argument("--timeout-min", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.max_units < 1 or args.timeout_min < 1:
        parser.error("max-units and timeout-min must be positive")
    lock = Path(git("rev-parse", "--git-common-dir")) / "harness-loop.lock"
    try:
        with lock.open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return run(args)
    except (RuntimeError, OSError, ValueError, ValidationError, subprocess.SubprocessError) as exc:
        print(f"Stopped: {exc}. Changes preserved; inspect before resuming.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
