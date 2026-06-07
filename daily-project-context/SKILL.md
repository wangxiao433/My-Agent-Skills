---
name: daily-project-context
description: Collect GitHub activity and local project logs for precise daily or weekly engineering reviews. Use when Codex should build a review packet from commits, issues, pull requests, comments, releases, simulation/training/build logs, JSON/YAML config, Markdown/JSON output, or saved report files.
---

# Daily Project Context

Use this skill to prepare evidence for an engineering daily or weekly review.
The helper script collects GitHub activity and local log excerpts, then renders a
Markdown or JSON packet. Treat the packet as evidence, not as complete truth.

## Workflow

1. Identify the GitHub username, local workspace path, date window, and timezone.
2. Ask for `repositories` and a GitHub token only when private repositories or
   richer PR/Issue data are required.
3. Run `scripts/gather_daily_project_context.py`.
4. Read the packet and produce the final review with:
   - review range
   - completed work with evidence
   - local errors, warnings, or blockers
   - missing context
   - next concrete actions
5. State when evidence is incomplete instead of inferring unseen work.

## Common Commands

Daily Markdown:

```bash
python daily-project-context/scripts/gather_daily_project_context.py \
  --github-username wangxiao433 \
  --workspace-path C:\Projects\Workspace \
  --date 2026-06-07
```

Weekly JSON with richer repository collection:

```bash
python daily-project-context/scripts/gather_daily_project_context.py \
  --github-username wangxiao433 \
  --workspace-path C:\Projects\Workspace \
  --period weekly \
  --date 2026-06-07 \
  --repo wangxiao433/My-Agent-Skills \
  --github-token %GITHUB_TOKEN% \
  --format json
```

Config file plus saved Markdown:

```bash
python daily-project-context/scripts/gather_daily_project_context.py \
  --config daily-project-context/examples/config.example.yaml \
  --output outputs/daily-review.md
```

## Evidence Rules

- Use `--since` and `--until` for exact inclusive date ranges.
- Use `--period weekly` for the trailing 7-day window ending at `--date`.
- Use `--repo owner/name` when private repositories or more complete repo data
  matter; public events alone can miss private activity.
- Use `--format json` when another tool or agent will consume the result.
- Use `--output path` when the report should be saved.
- Keep GitHub tokens out of final answers and logs.

## Safety

- Only scan directories explicitly provided by the user.
- Do not scan home directories, entire drives, or cloud-sync roots unless the user
  explicitly asks for that exact path.
- Respect scan limits: maximum files, maximum file bytes, and maximum matched
  lines per file.
- Treat logs as sensitive. The helper redacts common token/password patterns, but
  still inspect excerpts before sharing them externally.
- Prefer relative file paths in summaries.
- Do not upload local logs to third-party services unless the user explicitly asks.

## Files

- `scripts/gather_daily_project_context.py`: collector, renderer, CLI.
- `examples/config.example.yaml`: editable config template.
- `examples/sample_report.md`: representative Markdown output.
- `tests/test_gather_daily_project_context.py`: regression tests.
