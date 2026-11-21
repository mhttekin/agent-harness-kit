"""PreToolUse guard: chained `git commit`, `git push` and `git switch` must stop when a step fails.

It blocks a Bash command that runs one of those as one of several statements separated by `;`, a newline or a
background `&`, unless errexit is already on (`set -e`, `set -euo pipefail`, `set -o errexit`). Without it an
earlier step can fail (a branch that already exists, a refused commit) and the git step still runs. `&&`, `||` and
`|` keep a chain in one statement. Quoted strings, comments, `$(...)` and heredoc bodies that are data (a commit
message, a file) don't count; a heredoc fed to `bash`, `sh` or `zsh` is checked as a script, with errexit on when
that shell has `-e`. A guardrail, not a shell parser: `bash -c '...'` strings and `eval` aren't inspected.

Reads the hook's JSON on stdin (Claude Code and Codex share the shape); exit 2 with a reason on stderr blocks.
"""

import json
import re
import sys

GUARDED = ("commit", "push", "switch")
GIT = re.compile(
    r"(?:^|[\s(!{])git(?:\s+(?:-[Cc]\s+\S+|--?[\w-]+(?:=\S+)?))*\s+(?:" + "|".join(GUARDED) + r")\b"
)
SET = re.compile(r"^\s*set\s+((?:[-+]o\s+\w+|[-+][A-Za-z]+)(?:\s+(?:[-+]o\s+\w+|[-+][A-Za-z]+))*)")
SHELL = re.compile(r"(?:^|[\s;&|(])(?:\S*/)?(?:bash|sh|zsh)((?:\s+(?:-o\s+\w+|-[-\w]+))*)\s*$")
WORD_START = " \t\n;&|()"


def errexit_after(flags, current):
    """The errexit state after `set <flags>`: -e or -o errexit turn it on, +e or +o errexit turn it off."""
    tokens = flags.split()
    for index, token in enumerate(tokens):
        if token in ("-o", "+o") and index + 1 < len(tokens) and tokens[index + 1] == "errexit":
            current = token == "-o"
        elif token[0] in "-+" and token not in ("-o", "+o") and "e" in token[1:]:
            current = token[0] == "-"
    return current


def shell_errexit(flags):
    tokens = flags.split()
    if any(t == "-o" and n == "errexit" for t, n in zip(tokens, tokens[1:], strict=False)):
        return True
    return any(t.startswith("-") and not t.startswith("--") and "e" in t[1:] for t in tokens)


def skip_quoted(script, start, quote):
    """Index just past the closing quote (or the end of the script)."""
    index = start + 1
    while index < len(script):
        char = script[index]
        if quote == '"' and char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return index


def skip_substitution(script, start):
    """Index just past the `)` that closes the `$(` at start."""
    depth, index = 0, start + 1
    while index < len(script):
        char = script[index]
        if char in "'\"":
            index = skip_quoted(script, index, char)
            continue
        if char == "\\":
            index += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def heredoc_start(script, start):
    """(delimiter, strip_tabs, index after the operator and word) for the `<<` at start."""
    index = start + 2
    strip_tabs = index < len(script) and script[index] == "-"
    index += strip_tabs
    while index < len(script) and script[index] in " \t":
        index += 1
    word = []
    while index < len(script) and script[index] not in " \t\n;&|<>()":
        char = script[index]
        if char in "'\"":
            end = skip_quoted(script, index, char)
            word.append(script[index + 1 : end - 1])
            index = end
        elif char == "\\":
            word.append(script[index + 1 : index + 2])
            index += 2
        else:
            word.append(char)
            index += 1
    return "".join(word), strip_tabs, index


def statements(script):
    """[(text, [(text before <<, body)])]: text has quotes, comments and substitutions blanked."""
    found, current, heredocs, pending = [], [], [], []

    def flush():
        text = "".join(current).strip()
        if text or heredocs:
            found.append((text, list(heredocs)))
        current.clear()
        heredocs.clear()

    index = 0
    while index < len(script):
        char = script[index]
        following = script[index + 1 : index + 2]
        previous = script[index - 1] if index else "\n"
        if char == "\\":
            if following != "\n":
                current.append(script[index : index + 2])
            index += 2
        elif char in "'\"":
            index = skip_quoted(script, index, char)
            current.append(char * 2)
        elif char == "`":
            index = skip_quoted(script, index, "`")
            current.append("``")
        elif char == "$" and following == "(":
            index = skip_substitution(script, index + 1)
            current.append("$()")
        elif char == "#" and previous in WORD_START:
            while index < len(script) and script[index] != "\n":
                index += 1
        elif script.startswith("<<<", index):
            current.append("<<<")
            index += 3
        elif script.startswith("<<", index):
            delimiter, strip_tabs, index = heredoc_start(script, index)
            pending.append((delimiter, strip_tabs, "".join(current)))
            current.append("<<" + delimiter)
        elif char == "\n":
            index += 1
            for delimiter, strip_tabs, before in pending:
                body = []
                while index < len(script):
                    end = script.find("\n", index)
                    end = len(script) if end < 0 else end
                    line = script[index:end]
                    index = end + 1
                    if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                        break
                    body.append(line)
                heredocs.append((before, "\n".join(body)))
            pending.clear()
            flush()
        elif char == ";":
            flush()
            index += 2 if following == ";" else 1
        elif char == "&":
            if following == "&":
                current.append("&&")
                index += 2
            elif previous in "<>" or following == ">":
                current.append(char)
                index += 1
            else:
                flush()
                index += 1
        else:
            current.append(char)
            index += 1
    flush()
    return found


def problem(script, errexit=False):
    """Why the script must not run as it is, or None."""
    parts = statements(script)
    for text, heredocs in parts:
        flags = SET.match(text)
        if flags:
            errexit = errexit_after(flags.group(1), errexit)
        for before, body in heredocs:
            shell = SHELL.search(before.rstrip())
            if shell:
                nested = problem(body, errexit or shell_errexit(shell.group(1)))
                if nested:
                    return nested
        if len(parts) > 1 and not errexit and GIT.search(text):
            step = text if len(text) <= 100 else text[:97] + "..."
            return (
                f"Blocked: `{step}` is one of several commands separated by `;`, a newline or `&`, so it "
                "runs even when an earlier step failed. Chain the steps with `&&`, or start with "
                "`set -euo pipefail` (or run them in `bash -euo pipefail <<'EOF'`)."
            )
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return 0
    reason = problem(command)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
