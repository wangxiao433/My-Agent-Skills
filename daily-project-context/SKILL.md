---
name: daily-project-context
description: Collect GitHub activity and local project logs for a structured daily or weekly engineering review.
---

# Daily Project Context

Use this skill when the user wants a daily or weekly review of their engineering
work, especially when the review should combine GitHub activity with local
simulation, training, build, or debugging logs.

## Goal

Create a structured review packet that helps the assistant answer:

- What did the user do during the selected date range?
- Which repositories, issues, pull requests, or commits changed?
- Which local logs contain errors, warnings, convergence problems, NaN/OOM
  failures, timeouts, or other blockers?
- What is missing, risky, or worth doing next?

## Inputs

Ask for or infer these values before running the helper script:

- GitHub username.
- Local workspace path to scan.
- Date or date range.
- Timezone. Default to `UTC+8` when the user does not specify one.
- Optional GitHub token when private activity is required.
- Optional log extensions, keywords, excluded folders, and scan limits.

## Workflow

1. Run `scripts/gather_daily_project_context.py` with the user's GitHub username
   and workspace path.
2. Read the generated report packet.
3. Produce a human review with these sections:
   - Review date.
   - What was done.
   - Evidence from GitHub and local logs.
   - Problems, blockers, and likely causes.
   - Missing context.
   - Next actions.
4. If the data is thin or GitHub reports no public activity, say so directly and
   ask for the missing source instead of inventing progress.

## Safety

- Only scan directories explicitly provided by the user.
- Do not scan home directories, entire drives, or cloud-sync roots unless the user
  explicitly asks for that path.
- Respect the script's scan limits.
- Treat log contents as sensitive. Redact secrets, tokens, passwords, and API keys
  before including excerpts in the final answer.
- Prefer relative file paths in summaries when possible.
- Do not upload local logs to third-party services unless the user explicitly asks.

## Helper

Example command:

```bash
python daily-project-context/scripts/gather_daily_project_context.py \
  --github-username wangxiao433 \
  --workspace-path C:\Projects\Workspace \
  --date 2026-06-07 \
  --timezone-offset 8
```

The helper returns a Markdown packet. The packet is evidence for the assistant;
it is not the final user-facing review by itself.
