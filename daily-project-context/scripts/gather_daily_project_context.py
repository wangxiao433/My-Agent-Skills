"""Collect GitHub activity and local log evidence for engineering reviews."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_EXTENSIONS = (".log", ".txt", ".out", ".err")
DEFAULT_KEYWORDS = (
    "error",
    "warning",
    "failed",
    "failure",
    "fatal",
    "exception",
    "traceback",
    "assertion",
    "abort",
    "timeout",
    "killed",
    "memoryerror",
    "oom",
    "out of memory",
    "cuda out of memory",
    "nan",
    "inf",
    "infinity",
    "nonfinite",
    "overflow",
    "underflow",
    "divergence",
    "diverged",
    "converge",
    "residual",
    "loss exploded",
    "singular",
    "invalid",
    "segfault",
    "segmentation fault",
    "instability",
    "unstable",
    "cublas",
    "cudnn",
    "solver",
    "constraint",
    "floating point",
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
    re.compile(r"\b(ghp_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]+)\b"),
    re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{20,})\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*([^\s,;]+)"),
)


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime
    label: str


@dataclass(frozen=True)
class ScanConfig:
    github_username: str
    workspace_path: Path
    start_date: date
    end_date: date
    timezone_offset_hours: int = 8
    github_token: str | None = None
    repositories: tuple[str, ...] = ()
    include_public_events: bool = True
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    excluded_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_DIRS))
    max_files: int = 40
    max_file_bytes: int = 1_000_000
    max_lines_per_file: int = 50
    max_github_items: int = 100
    output_format: str = "markdown"
    include_review: bool = True
    review_language: str = "zh"


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def normalize_extension(value: str) -> str:
    value = value.strip()
    return value if value.startswith(".") else f".{value}"


def local_window(start_date: date, end_date: date, timezone_offset_hours: int) -> TimeWindow:
    if end_date < start_date:
        raise ValueError("--until must be the same as or later than --since")
    tz = timezone(timedelta(hours=timezone_offset_hours))
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    if start_date == end_date:
        label = start_date.isoformat()
    else:
        label = f"{start_date.isoformat()} to {end_date.isoformat()}"
    return TimeWindow(start=start, end=end, label=label)


def parse_github_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact_secret(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def request_json(url: str, token: str | None = None, params: dict[str, str] | None = None) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "daily-project-context-skill",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def event_time_in_window(value: str | None, window: TimeWindow) -> bool:
    if not value:
        return False
    event_time = parse_github_time(value).astimezone(window.start.tzinfo)
    return window.start <= event_time < window.end


def add_record(records: list[dict[str, Any]], **kwargs: Any) -> None:
    records.append({key: value for key, value in kwargs.items() if value not in (None, "", [])})


def summarize_public_event(event: dict[str, Any], window: TimeWindow) -> list[dict[str, Any]]:
    repo_name = event.get("repo", {}).get("name", "unknown repository")
    payload = event.get("payload", {})
    event_type = event.get("type", "UnknownEvent")
    timestamp = event.get("created_at")
    records: list[dict[str, Any]] = []

    if event_type == "PushEvent":
        commits = payload.get("commits", [])
        if not commits:
            add_record(records, source="github_public_events", kind="push", repo=repo_name, summary="pushed commits", timestamp=timestamp)
        for commit in commits:
            sha = commit.get("sha")
            add_record(
                records,
                source="github_public_events",
                kind="commit",
                repo=repo_name,
                summary=commit.get("message", "").strip() or "(no message)",
                timestamp=timestamp,
                url=f"https://github.com/{repo_name}/commit/{sha}" if sha else None,
            )
        return records

    if event_type == "IssuesEvent":
        issue = payload.get("issue", {})
        add_record(
            records,
            source="github_public_events",
            kind="issue",
            repo=repo_name,
            summary=f"{payload.get('action', 'updated')} - {issue.get('title', '')}".strip(),
            timestamp=timestamp,
            url=issue.get("html_url"),
        )
        return records

    if event_type == "PullRequestEvent":
        pull_request = payload.get("pull_request", {})
        add_record(
            records,
            source="github_public_events",
            kind="pull_request",
            repo=repo_name,
            summary=f"{payload.get('action', 'updated')} - {pull_request.get('title', '')}".strip(),
            timestamp=timestamp,
            url=pull_request.get("html_url"),
        )
        return records

    if event_type in {"IssueCommentEvent", "PullRequestReviewEvent", "PullRequestReviewCommentEvent"}:
        add_record(records, source="github_public_events", kind="review_or_comment", repo=repo_name, summary=payload.get("action", "updated"), timestamp=timestamp)
        return records

    if event_type == "ReleaseEvent":
        release = payload.get("release", {})
        add_record(
            records,
            source="github_public_events",
            kind="release",
            repo=repo_name,
            summary=f"{payload.get('action', 'updated')} - {release.get('name', '')}".strip(),
            timestamp=timestamp,
            url=release.get("html_url"),
        )
        return records

    if event_type == "CreateEvent":
        ref_type = payload.get("ref_type", "ref")
        ref = payload.get("ref") or repo_name
        add_record(records, source="github_public_events", kind="create", repo=repo_name, summary=f"created {ref_type} {ref}", timestamp=timestamp)
        return records

    add_record(records, source="github_public_events", kind=event_type, repo=repo_name, summary="captured activity", timestamp=timestamp)
    return records


def fetch_public_github_records(config: ScanConfig, window: TimeWindow) -> tuple[list[dict[str, Any]], list[str]]:
    if not config.include_public_events:
        return [], []
    try:
        events = request_json(
            f"https://api.github.com/users/{config.github_username}/events",
            token=config.github_token,
            params={"per_page": str(min(config.max_github_items, 100))},
        )
    except Exception as exc:
        return [], [f"GitHub public events failed: {exc}"]

    records: list[dict[str, Any]] = []
    for event in events:
        if event_time_in_window(event.get("created_at"), window):
            records.extend(summarize_public_event(event, window))
    return records, []


def fetch_repository_records(config: ScanConfig, window: TimeWindow) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not config.repositories:
        return records, errors

    since = iso_utc(window.start)
    until = iso_utc(window.end)
    for repo in config.repositories:
        try:
            commits = request_json(
                f"https://api.github.com/repos/{repo}/commits",
                token=config.github_token,
                params={
                    "author": config.github_username,
                    "since": since,
                    "until": until,
                    "per_page": str(min(config.max_github_items, 100)),
                },
            )
            for commit in commits:
                commit_data = commit.get("commit", {})
                add_record(
                    records,
                    source="github_repo_commits",
                    kind="commit",
                    repo=repo,
                    summary=commit_data.get("message", "").splitlines()[0],
                    timestamp=commit_data.get("author", {}).get("date"),
                    url=commit.get("html_url"),
                )
        except Exception as exc:
            errors.append(f"Repo commits failed for {repo}: {exc}")

        try:
            issues = request_json(
                f"https://api.github.com/repos/{repo}/issues",
                token=config.github_token,
                params={
                    "state": "all",
                    "since": since,
                    "per_page": str(min(config.max_github_items, 100)),
                },
            )
            for issue in issues:
                timestamps = (issue.get("created_at"), issue.get("updated_at"), issue.get("closed_at"))
                if not any(event_time_in_window(item, window) for item in timestamps):
                    continue
                kind = "pull_request" if issue.get("pull_request") else "issue"
                add_record(
                    records,
                    source="github_repo_issues",
                    kind=kind,
                    repo=repo,
                    summary=f"{issue.get('state', 'unknown')} - {issue.get('title', '')}",
                    timestamp=issue.get("updated_at") or issue.get("created_at"),
                    url=issue.get("html_url"),
                )
        except Exception as exc:
            errors.append(f"Repo issues failed for {repo}: {exc}")

        try:
            pulls = request_json(
                f"https://api.github.com/repos/{repo}/pulls",
                token=config.github_token,
                params={
                    "state": "all",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": str(min(config.max_github_items, 100)),
                },
            )
            for pull in pulls:
                timestamps = (pull.get("created_at"), pull.get("updated_at"), pull.get("closed_at"), pull.get("merged_at"))
                if not any(event_time_in_window(item, window) for item in timestamps):
                    continue
                state = "merged" if pull.get("merged_at") else pull.get("state", "unknown")
                add_record(
                    records,
                    source="github_repo_pulls",
                    kind="pull_request",
                    repo=repo,
                    summary=f"{state} - {pull.get('title', '')}",
                    timestamp=pull.get("updated_at") or pull.get("created_at"),
                    url=pull.get("html_url"),
                )
        except Exception as exc:
            errors.append(f"Repo pulls failed for {repo}: {exc}")

    return dedupe_records(records), errors


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        key = (record.get("kind"), record.get("repo"), record.get("summary"), record.get("url"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def collect_github_records(config: ScanConfig, window: TimeWindow, events: Iterable[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    if events is not None:
        records: list[dict[str, Any]] = []
        for event in events:
            if event_time_in_window(event.get("created_at"), window):
                records.extend(summarize_public_event(event, window))
        return records, []

    public_records, public_errors = fetch_public_github_records(config, window)
    repo_records, repo_errors = fetch_repository_records(config, window)
    return dedupe_records(public_records + repo_records), public_errors + repo_errors


def iter_candidate_log_files(config: ScanConfig, window: TimeWindow) -> list[Path]:
    if not config.workspace_path.exists():
        return []

    candidates: list[tuple[float, Path]] = []
    for root, dirs, files in os.walk(config.workspace_path):
        root_path = Path(root)
        dirs[:] = [name for name in dirs if name not in config.excluded_dirs]
        relative_root = root_path.relative_to(config.workspace_path)
        if any(part in config.excluded_dirs for part in relative_root.parts):
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
            modified = datetime.fromtimestamp(stat.st_mtime, tz=window.start.tzinfo)
            if window.start <= modified < window.end:
                candidates.append((stat.st_mtime, file_path))

    candidates.sort(reverse=True)
    return [path for _, path in candidates[: config.max_files]]


def keyword_matches(text: str, keywords: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lowered]


def collect_log_matches(file_path: Path, config: ScanConfig) -> dict[str, Any]:
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return {"path": str(file_path), "error": f"Read failed: {exc}", "matches": []}

    matches = []
    for line_number, line in enumerate(lines, start=1):
        matched_keywords = keyword_matches(line, config.keywords)
        if not matched_keywords:
            continue
        matches.append(
            {
                "line": line_number,
                "keywords": matched_keywords,
                "text": redact_secret(line.strip()),
            }
        )
        if len(matches) >= config.max_lines_per_file:
            break

    return {"matches": matches, "line_count": len(lines)}


def collect_local_logs(config: ScanConfig, window: TimeWindow) -> tuple[list[dict[str, Any]], list[str]]:
    if not config.workspace_path.exists():
        return [], [f"Workspace not found: {config.workspace_path}"]

    records: list[dict[str, Any]] = []
    for file_path in iter_candidate_log_files(config, window):
        relative = file_path.relative_to(config.workspace_path)
        stat = file_path.stat()
        result = collect_log_matches(file_path, config)
        records.append(
            {
                "path": str(relative),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=window.start.tzinfo).isoformat(),
                "size_bytes": stat.st_size,
                "line_count": result.get("line_count"),
                "matches": result.get("matches", []),
                "error": result.get("error"),
            }
        )
    return records, []


def build_review(scope: dict[str, Any], github_records: list[dict[str, Any]], log_records: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    matched_logs = [record for record in log_records if record.get("matches")]
    risk_keywords: dict[str, int] = {}
    for record in matched_logs:
        for match in record.get("matches", []):
            for keyword in match.get("keywords", []):
                risk_keywords[keyword] = risk_keywords.get(keyword, 0) + 1

    next_actions = []
    if matched_logs:
        next_actions.append("逐个打开 Local Logs 中有匹配行的文件，优先处理 error/fatal/oom/nan/timeout 等高风险项。")
    if not github_records:
        next_actions.append("补充 GitHub token 或 repositories 配置，以确认是否存在私有仓库活动。")
    if errors:
        next_actions.append("先处理采集错误，避免复盘基于不完整证据。")
    if not next_actions:
        next_actions.append("基于已捕获证据整理完成项，并补充人工判断的下一步计划。")

    missing_context = [
        "没有配置 repositories 时，私有仓库和更完整的 PR/Issue 数据可能缺失。"
        if not scope.get("repositories")
        else "",
        "GitHub API 错误会导致线上活动证据不完整。" if errors else "",
        "没有匹配日志关键词不等于没有问题，只表示当前规则未捕获到证据。" if not matched_logs else "",
    ]

    return {
        "language": "zh",
        "evidence_note": "以下复盘草稿只基于采集到的 GitHub 记录和本地日志证据，不推断未出现的事实。",
        "captured_progress_count": len(github_records),
        "matched_log_file_count": len(matched_logs),
        "top_risk_keywords": sorted(risk_keywords.items(), key=lambda item: (-item[1], item[0]))[:10],
        "missing_context": [item for item in missing_context if item],
        "next_actions": next_actions,
    }


def build_report(config: ScanConfig, events: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
    window = local_window(config.start_date, config.end_date, config.timezone_offset_hours)
    github_records, github_errors = collect_github_records(config, window, events=events)
    log_records, log_errors = collect_local_logs(config, window)
    errors = github_errors + log_errors
    scope = {
        "github_username": config.github_username,
        "workspace_path": str(config.workspace_path),
        "window_label": window.label,
        "start": window.start.isoformat(),
        "end_exclusive": window.end.isoformat(),
        "timezone_offset_hours": config.timezone_offset_hours,
        "repositories": list(config.repositories),
        "extensions": list(config.extensions),
        "max_files": config.max_files,
        "max_file_bytes": config.max_file_bytes,
    }
    report = {
        "scope": scope,
        "github_activity": github_records,
        "local_logs": log_records,
        "errors": errors,
    }
    if config.include_review:
        report["review"] = build_review(scope, github_records, log_records, errors)
    return report


def github_record_to_line(record: dict[str, Any]) -> str:
    text = f"- [{record.get('kind', 'activity')}] {record.get('repo', 'unknown')}: {record.get('summary', '')}"
    if record.get("timestamp"):
        text += f" ({record['timestamp']})"
    if record.get("url"):
        text += f" - {record['url']}"
    return text


def render_markdown(report: dict[str, Any]) -> str:
    scope = report["scope"]
    lines = [
        f"# Project Context Review: {scope['window_label']}",
        "",
        "## Scope",
        f"- GitHub user: {scope['github_username']}",
        f"- Workspace: {scope['workspace_path']}",
        f"- Time window: {scope['start']} to {scope['end_exclusive']} (end exclusive)",
        f"- Repositories: {', '.join(scope['repositories']) if scope['repositories'] else '(not configured)'}",
        "",
        "## GitHub Activity",
    ]

    github_records = report.get("github_activity", [])
    if github_records:
        lines.extend(github_record_to_line(record) for record in github_records)
    else:
        lines.append("- No GitHub activity was captured in the selected window.")

    lines.extend(["", "## Local Logs"])
    local_logs = report.get("local_logs", [])
    if not local_logs:
        lines.append("- No updated log files were found in the selected window.")
    for record in local_logs:
        lines.append(f"- {record['path']} ({record.get('modified_at')}, {record.get('size_bytes')} bytes)")
        if record.get("error"):
            lines.append(f"  - {record['error']}")
        matches = record.get("matches", [])
        if not matches:
            lines.append("  - File changed, but no configured keyword was found.")
        for match in matches:
            keyword_text = ", ".join(match.get("keywords", []))
            lines.append(f"  - Line {match.get('line')} [{keyword_text}]: {match.get('text')}")

    if report.get("errors"):
        lines.extend(["", "## Collection Errors"])
        lines.extend(f"- {error}" for error in report["errors"])

    review = report.get("review")
    if review:
        lines.extend(
            [
                "",
                "## 中文复盘草稿",
                f"- 证据边界: {review['evidence_note']}",
                f"- 捕获到的 GitHub 记录数: {review['captured_progress_count']}",
                f"- 命中关键词的日志文件数: {review['matched_log_file_count']}",
            ]
        )
        if review.get("top_risk_keywords"):
            keyword_summary = ", ".join(f"{keyword} x{count}" for keyword, count in review["top_risk_keywords"])
            lines.append(f"- 高风险关键词: {keyword_summary}")
        missing_context = [item for item in review.get("missing_context", []) if item]
        if missing_context:
            lines.append("- 缺失上下文:")
            lines.extend(f"  - {item}" for item in missing_context)
        lines.append("- 下一步建议:")
        lines.extend(f"  - {item}" for item in review.get("next_actions", []))

    lines.extend(
        [
            "",
            "## Assistant Review Checklist",
            "- Summarize completed work with direct evidence.",
            "- Connect GitHub activity to relevant local errors or warnings.",
            "- Call out missing context instead of guessing.",
            "- Propose the next concrete actions.",
        ]
    )
    return "\n".join(lines)


def render_report(report: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    return render_markdown(report)


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        return value.strip("'\"")


def load_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current_key:
            data.setdefault(current_key, []).append(parse_scalar(stripped[2:]))
            continue
        if ":" not in line:
            raise ValueError(f"Unsupported config line: {raw_line}")
        key, value = line.split(":", 1)
        current_key = key.strip().replace("-", "_")
        parsed = parse_scalar(value)
        data[current_key] = [] if parsed == "" else parsed
    return data


def load_config(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() in {".yaml", ".yml"}:
        return load_simple_yaml(text)
    raise ValueError("Config file must be .json, .yaml, or .yml")


def split_csv(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        result.extend(item.strip() for item in value.split(",") if item.strip())
    return result


def ensure_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return split_csv([value])
    return [str(item) for item in value]


def config_value(data: dict[str, Any], key: str, default: Any = None) -> Any:
    return data.get(key, default)


def build_config(args: argparse.Namespace) -> ScanConfig:
    config_data = load_config(Path(args.config)) if args.config else {}
    tz_offset = args.timezone_offset if args.timezone_offset is not None else int(config_value(config_data, "timezone_offset", 8))
    tz = timezone(timedelta(hours=tz_offset))

    github_username = args.github_username or config_value(config_data, "github_username")
    workspace_path = args.workspace_path or config_value(config_data, "workspace_path")
    if not github_username:
        raise ValueError("github_username is required through --github-username or config")
    if not workspace_path:
        raise ValueError("workspace_path is required through --workspace-path or config")

    today = datetime.now(tz).date()
    date_arg = args.date or config_value(config_data, "date")
    until_arg = args.until or config_value(config_data, "until")
    since_arg = args.since or config_value(config_data, "since")
    period = args.period or config_value(config_data, "period", "daily")
    days = args.days if args.days is not None else config_value(config_data, "days")

    end_date = parse_date(until_arg) if until_arg else parse_date(date_arg) if date_arg else today
    if since_arg:
        start_date = parse_date(since_arg)
    elif days:
        start_date = end_date - timedelta(days=int(days) - 1)
    elif period == "weekly":
        start_date = end_date - timedelta(days=6)
    else:
        start_date = end_date

    repositories = tuple(split_csv(args.repo) or ensure_list(config_value(config_data, "repositories", [])))
    extensions = tuple(normalize_extension(item) for item in (split_csv(args.extension) or ensure_list(config_value(config_data, "extensions", DEFAULT_EXTENSIONS))))
    keywords = tuple(split_csv(args.keyword) or ensure_list(config_value(config_data, "keywords", DEFAULT_KEYWORDS)))
    excluded_dirs = set(split_csv(args.exclude_dir) or ensure_list(config_value(config_data, "excluded_dirs", DEFAULT_EXCLUDED_DIRS)))

    return ScanConfig(
        github_username=str(github_username),
        workspace_path=Path(str(workspace_path)),
        start_date=start_date,
        end_date=end_date,
        timezone_offset_hours=tz_offset,
        github_token=args.github_token or config_value(config_data, "github_token"),
        repositories=repositories,
        include_public_events=bool(config_value(config_data, "include_public_events", True)) if args.no_public_events is False else False,
        extensions=extensions,
        keywords=keywords,
        excluded_dirs=excluded_dirs,
        max_files=int(args.max_files if args.max_files is not None else config_value(config_data, "max_files", 40)),
        max_file_bytes=int(args.max_file_bytes if args.max_file_bytes is not None else config_value(config_data, "max_file_bytes", 1_000_000)),
        max_lines_per_file=int(args.max_lines_per_file if args.max_lines_per_file is not None else config_value(config_data, "max_lines_per_file", 50)),
        max_github_items=int(args.max_github_items if args.max_github_items is not None else config_value(config_data, "max_github_items", 100)),
        output_format=args.format or config_value(config_data, "format", "markdown"),
        include_review=not args.no_review,
        review_language=str(config_value(config_data, "review_language", "zh")),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Optional .json/.yaml config file. CLI values override config values.")
    parser.add_argument("--github-username")
    parser.add_argument("--workspace-path")
    parser.add_argument("--date", help="Target local date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--since", help="Start date, inclusive, in YYYY-MM-DD format.")
    parser.add_argument("--until", help="End date, inclusive, in YYYY-MM-DD format.")
    parser.add_argument("--period", choices=("daily", "weekly"), help="Use daily or trailing 7-day weekly window.")
    parser.add_argument("--days", type=int, help="Trailing N-day window ending at --date/--until.")
    parser.add_argument("--timezone-offset", type=int)
    parser.add_argument("--github-token")
    parser.add_argument("--repo", action="append", help="Repository full name. Can be repeated or comma-separated.")
    parser.add_argument("--extension", action="append", help="Log extension. Can be repeated or comma-separated.")
    parser.add_argument("--keyword", action="append", help="Keyword. Can be repeated or comma-separated.")
    parser.add_argument("--exclude-dir", action="append", help="Directory name to exclude. Can be repeated or comma-separated.")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--max-file-bytes", type=int)
    parser.add_argument("--max-lines-per-file", type=int)
    parser.add_argument("--max-github-items", type=int)
    parser.add_argument("--format", choices=("markdown", "json"))
    parser.add_argument("--output", help="Optional path to write the rendered report.")
    parser.add_argument("--no-review", action="store_true", help="Do not include the deterministic Chinese review draft.")
    parser.add_argument("--no-public-events", action="store_true", help="Skip GitHub public events collection.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        config = build_config(args)
        report = build_report(config)
        rendered = render_report(report, config.output_format)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
        print(rendered)
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
