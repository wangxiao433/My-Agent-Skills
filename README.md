# My Agent Skills

This repository stores personal agent skills. Each skill lives in its own folder
and includes a `SKILL.md` file plus helper scripts, examples, and tests.

## Skills

- `daily-project-context`: Collects GitHub activity and local engineering logs,
  then prepares a precise daily or weekly review packet for an AI assistant.

## Repository Layout

```text
daily-project-context/
  SKILL.md
  scripts/
    gather_daily_project_context.py
  examples/
    config.example.yaml
    sample_report.md
  tests/
    test_gather_daily_project_context.py
```

## Usage

Daily review:

```bash
python daily-project-context/scripts/gather_daily_project_context.py \
  --github-username wangxiao433 \
  --workspace-path C:\Projects\Workspace \
  --date 2026-06-07
```

Weekly JSON review with richer repository data:

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

Config file and saved output:

```bash
python daily-project-context/scripts/gather_daily_project_context.py \
  --config daily-project-context/examples/config.example.yaml \
  --output outputs/daily-review.md
```

## Development

Run the tests with:

```bash
python -m unittest discover -s daily-project-context/tests
```

The repository now uses a structured skill package layout.
