---
name: review
description: Review a staged diff, range, or patch against rules derived from AGENTS.md.
---

# Review

Read AGENTS.md and relevant docs/decisions first. Review only the supplied diff:
no argument means `git diff --staged`; a range means `git diff <range>`; a patch
path means read it, never apply it. Include new files in a supplied patch.
Use fresh context when available. Do not run formatting or edit files.

## Rules

<!-- Bootstrap replaces this list with numbered rules derived ONLY from this
project's AGENTS.md. Each rule names its source invariant and concrete violation.
R1: <AGENTS invariant; evidence that constitutes a violation>.
Do not invent product rules or copy rules from another repository. -->

If no rules are configured, report `VERDICT: UNCONFIGURED`; never imply coverage.
Computational gates own lint and tests; don't repeat them. Report only concrete
violations with a quoted diff line and source invariant:

```
[R1] path:line
> diff line
Why it violates the cited invariant.
```

End with exactly `VERDICT: PASS` or `VERDICT: FAIL` when configured.
