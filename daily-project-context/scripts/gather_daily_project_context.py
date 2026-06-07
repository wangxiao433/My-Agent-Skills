"""Collect GitHub activity and local log excerpts for an engineering review."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_EXTENSIONS = (".log", ".txt", ".out", ".err")
DEFAULT_KEYWORDS = (
    "error",
    "warning",
    "failed",
    "failure",
    "converge",
    "nan",
    "oom",
    "out of memory",
    "divergence",
    "fatal",
    "exception",
    "timeout",
)
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
}
SECRET_PATTERNS = (
    re.compile(r"(ghp_[A-Za-z0-9_]{20,})"),
    re.compile(r"(github_pat_[A-Za-z0-9_]+)"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)"),
)


@dataclass(frozen=True)
class ScanConfig:
    github_username: str
    workspace_path: Path
    target_date: date
    timezone_offset_hours: int = 8
    github_token: str | None = None
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    excluded_dirs: set[str] | None = None
    max_files: int = 40
    max_file_bytes: int = 1_000_000
    max_lines_per_file: int = 50


def local_day_window(target_date: date, timezone_offset_hours: int) -> tuple[datetime, datetime]:
    tz = timezone(timedelta(hours=timezone_offset_hours))
    start = datetime.combine(target_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def parse_github_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def redact_secret(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def fetch_public_github_events(username: str, token: str | None = None) -> list[dict[str, Any]]:
    url = f"https://api.github.com/users/{username}/events"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "daily-project-context-skill",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def summarize_github_event(event: dict[str, Any]) -> list[str]:
    repo_name = event.get("repo", {}).get("name", "unknown repository")
    payload = event.get("payload", {})
    event_type = event.get("type", "UnknownEvent")

    if event_type == "PushEvent":
        commits = payload.get("commits", [])
        if not commits:
            return [f"- [Push] {repo_name}: pushed commits"]
        return [
            f"- [Commit] {repo_name}: {commit.get('message', '').strip() or '(no message)'}"
            for commit in commits
        ]

    if event_type == "IssuesEvent":
        issue = payload.get("issue", {})
        return [f"- [Issue] {repo_name}: {payload.get('action', 'updated')} - {issue.get('title', '')}"]

    if event_type == "PullRequestEvent":
        pull_request = payload.get("pull_request", {})
        return [
            f"- [Pull Request] {repo_name}: {payload.get('action', 'updated')} - "
            f"{pull_request.get('title', '')}"
        ]

    if event_type in {"IssueCommentEvent", "PullRequestReviewEvent", "PullRequestReviewCommentEvent"}:
        return [f"- [Review/Comment] {repo_name}: {payload.get('action', 'updated')}"]

    if event_type == "ReleaseEvent":
        release = payload.get("release", {})
        return [f"- [Release] {repo_name}: {payload.get('action', 'updated')} - {release.get('name', '')}"]

    if event_type == "CreateEvent":
        ref_type = payload.get("ref_type", "ref")
        ref = payload.get("ref") or repo_name
        return [f"- [Create] {repo_name}: created {ref_type} {ref}"]

    return [f"- [{event_type}] {repo_name}: captured activity"]


def collect_github_lines(
    events: Iterable[dict[str, Any]],
    start: datetime,
    end: datetime,
    timezone_offset_hours: int,
) -> list[str]:
    tz = timezone(timedelta(hours=timezone_offset_hours))
    lines: list[str] = []
    for event in events:
        created_at = event.get("created_at")
        if not created_at:
            continue
        event_time = parse_github_time(created_at).astimezone(tz)
        if start <= event_time < end:
            lines.extend(summarize_github_event(event))
    return lines


def should_skip_dir(path: Path, excluded_dirs: set[str]) -> bool:
    return any(part in excluded_dirs for part in path.parts)


def iter_candidate_log_files(config: ScanConfig, start: datetime, end: datetime) -> list[Path]:
    if not config.workspace_path.exists():
        return []

    excluded_dirs = config.excluded_dirs or DEFAULT_EXCLUDED_DIRS
    candidates: list[tuple[float, Path]] = []
    for root, dirs, files in os.walk(config.workspace_path):
        root_path = Path(root)
        dirs[:] = [name for name in dirs if name not in excluded_dirs]
        if should_skip_dir(root_path.relative_to(config.workspace_path), excluded_dirs):
            continue

        for file_name in files:
            file_path = root_path / file_name
            if file_path.suffix.lower() not in config.extensions:
                continue
            try:
                stat = file_path.stat()
            except OSError:
                continue
            if stat.st_size > config.max_file_bytes:
                continue
            modified = datetime.fromtimestamp(stat.st_mtime, tz=start.tzinfo)
            if start <= modified < end:
                candidates.append((stat.st_mtime, file_path))

    candidates.sort(reverse=True)
    return [path for _, path in candidates[: config.max_files]]


def collect_log_excerpt(file_path: Path, config: ScanConfig) -> list[str]:
    keyword_pattern = re.compile("|".join(re.escape(keyword) for keyword in config.keywords), re.IGNORECASE)
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return [f"  - Read failed: {exc}"]

    if len(lines) <= config.max_lines_per_file:
        excerpt = [line.strip() for line in lines if line.strip()]
    else:
        excerpt = [
            f"Line {line_number}: {line.strip()}"
            for line_number, line in enumerate(lines, start=1)
            if keyword_pattern.search(line)
        ]

    if not excerpt:
        return ["  - File changed, but no configured keyword was found."]

    return [f"  - {redact_secret(line)}" for line in excerpt[: config.max_lines_per_file]]


def collect_local_log_lines(config: ScanConfig, start: datetime, end: datetime) -> list[str]:
    if not config.workspace_path.exists():
        return [f"- Workspace not found: {config.workspace_path}"]

    files = iter_candidate_log_files(config, start, end)
    if not files:
        return ["- No updated log files were found in the selected date window."]

    lines: list[str] = []
    for file_path in files:
        relative = file_path.relative_to(config.workspace_path)
        lines.append(f"- {relative}")
        lines.extend(collect_log_excerpt(file_path, config))
    return lines


def gather_daily_project_context(config: ScanConfig, events: Iterable[dict[str, Any]] | None = None) -> str:
    start, end = local_day_window(config.target_date, config.timezone_offset_hours)

    report = [
        f"# Daily Project Context: {config.target_date.isoformat()}",
        "",
        "## Scope",
        f"- GitHub user: {config.github_username}",
        f"- Workspace: {config.workspace_path}",
        f"- Time window: {start.isoformat()} to {end.isoformat()}",
        "",
        "## GitHub Activity",
    ]

    try:
        github_events = list(events) if events is not None else fetch_public_github_events(
            config.github_username,
            config.github_token,
        )
        github_lines = collect_github_lines(github_events, start, end, config.timezone_offset_hours)
    except Exception as exc:
        github_lines = [f"- GitHub collection failed: {exc}"]

    report.extend(github_lines or ["- No public GitHub activity was found in the selected date window."])
    report.extend(["", "## Local Logs"])
    report.extend(collect_local_log_lines(config, start, end))
    report.extend(
        [
            "",
            "## Assistant Review Checklist",
            "- Summarize completed work with evidence.",
            "- Connect GitHub activity to relevant local errors or warnings.",
            "- Call out missing context instead of guessing.",
            "- Propose the next concrete actions.",
        ]
    )
    return "\n".join(report)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-username", required=True)
    parser.add_argument("--workspace-path", required=True)
    parser.add_argument("--date", help="Target local date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--timezone-offset", type=int, default=8)
    parser.add_argument("--github-token", default=None)
    parser.add_argument("--max-files", type=int, default=40)
    parser.add_argument("--max-file-bytes", type=int, default=1_000_000)
    parser.add_argument("--max-lines-per-file", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tz = timezone(timedelta(hours=args.timezone_offset))
    target_date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
    config = ScanConfig(
        github_username=args.github_username,
        workspace_path=Path(args.workspace_path),
        target_date=target_date,
        timezone_offset_hours=args.timezone_offset,
        github_token=args.github_token,
        max_files=args.max_files,
        max_file_bytes=args.max_file_bytes,
        max_lines_per_file=args.max_lines_per_file,
    )
    print(gather_daily_project_context(config))


if __name__ == "__main__":
    main()
