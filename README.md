# My Agent Skills

This repository stores personal agent skills. Each skill should live in its own
folder and include a `SKILL.md` file plus any helper scripts, examples, and tests.

## Skills

- `daily-project-context`: Collects GitHub activity and local engineering logs,
  then prepares a structured daily or weekly review context for an AI assistant.

## Repository Layout

```text
daily-project-context/
  SKILL.md
  scripts/
    gather_daily_project_context.py
  examples/
    sample_report.md
  tests/
    test_gather_daily_project_context.py
```

## Development

Run the tests with:

```bash
python -m unittest discover -s daily-project-context/tests
```

The structured skill package has been added alongside the original single-file
draft so the draft can be reviewed before it is removed.
