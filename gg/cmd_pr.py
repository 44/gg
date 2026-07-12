import html
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import uuid
from urllib.parse import quote

from rich.console import Console
from rich.text import Text

from .utils import run

console = Console()


def cmd_pr(args):
    command = args.pr_command
    commands = {
        "list": cmd_pr_list,
        "publish": cmd_pr_publish,
        "cache": cmd_pr_cache,
        "show": cmd_pr_show,
        "review": cmd_pr_review,
        "respond": cmd_pr_respond,
        "manage": cmd_pr_manage,
        "_manage": cmd_pr_manage_sync,
        "_manage-reload": cmd_pr_manage_reload,
        "_manage-changes": cmd_pr_manage_changes,
        "_manage-diff-open": cmd_pr_manage_diff_open,
        "_manage-threads": cmd_pr_manage_threads,
        "_manage-thread-new": cmd_pr_manage_thread_new,
        "_manage-thread-open": cmd_pr_manage_thread_open,
        "_manage-thread-status": cmd_pr_manage_thread_status,
        "_manage-policies": cmd_pr_manage_policies,
        "_manage-policy-cancel": cmd_pr_manage_policy_cancel,
        "_manage-policy-queue": cmd_pr_manage_policy_queue,
        "_set-status": cmd_pr_set_status,
        "_set-vote": cmd_pr_set_vote,
        "_fetch-summary": cmd_pr_fetch_summary,
        "_publish": cmd_pr_publish_data,
    }
    if command in commands:
        return commands[command](args)
    print(f"Unknown pr command: {command}", file=sys.stderr)
    return 1


def _get_git_email():
    result = run(["git", "config", "user.email"])
    if result.returncode != 0:
        print(
            "Failed to get git user email. Ensure git config user.email is set.",
            file=sys.stderr,
        )
        return None
    return result.stdout.strip()


def _ensure_path():
    paths = os.environ.get("PATH", "").split(os.pathsep)
    user_bin = os.path.expanduser("~/.local/bin")
    if user_bin not in paths:
        os.environ["PATH"] = f"{user_bin}{os.pathsep}{os.environ['PATH']}"


def _run_az(cmd, timeout=None):
    _ensure_path()
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            shell=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            cmd,
            124,
            stdout=exc.stdout or "",
            stderr=f"command timed out after {timeout}s",
        )


def _sync_branch(branch):
    result = run(["git", "branch", "--list", branch])
    if result.returncode != 0 or not result.stdout.strip():
        return

    run(["git", "fetch", "origin", f"{branch}:{branch}"])
    run(["git", "push", "origin", branch])


def cmd_pr_publish(args):
    pr_id = args.pr_id

    result = _run_az(f"az repos pr show --id {pr_id} --output json")
    if result.returncode != 0:
        print(f"az command failed: {result.stderr}", file=sys.stderr)
        return 1

    try:
        pr = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Failed to parse az output as JSON.", file=sys.stderr)
        return 1

    title = pr.get("title", "")
    description = pr.get("description") or ""
    is_draft = pr.get("isDraft", False)
    branch = pr.get("sourceRefName", "").removeprefix("refs/heads/")

    if branch:
        print(f"Syncing branch: {branch}", file=sys.stderr)
        _sync_branch(branch)

    original = (title, description)

    if args.file:
        with open(args.file, "r") as f:
            content = f.read().strip()
        if not content:
            print("File is empty.", file=sys.stderr)
            return 1
        lines = content.split("\n", 1)
        new_title = lines[0].strip()
        new_description = lines[1].strip() if len(lines) > 1 else ""
    else:
        fd, temp_path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w") as f:
            f.write(f"{title}\n")
            if description:
                f.write(f"{description}\n")

        subprocess.run(["nvim", temp_path])

        with open(temp_path, "r") as f:
            content = f.read().strip()
        os.unlink(temp_path)

        if not content:
            print("No content saved, aborting.", file=sys.stderr)
            return 1

        lines = content.split("\n", 1)
        new_title = lines[0].strip()
        new_description = lines[1].strip() if len(lines) > 1 else ""

    changed = (new_title, new_description) != original

    if not changed and not is_draft:
        print("No changes and PR is already published.", file=sys.stderr)
        return 0

    body = {}
    if changed:
        body["title"] = new_title
        body["description"] = new_description
    if is_draft:
        body["isDraft"] = False

    fd, body_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(body, f)

    api_url = pr["url"]
    if "api-version" not in api_url:
        api_url += "?api-version=7.1"

    cmd = f"az rest --method PATCH --url {shlex.quote(api_url)} --body @{shlex.quote(body_path)} --headers Content-Type=application/json --resource https://app.vssps.visualstudio.com"
    result = _run_az(cmd)
    os.unlink(body_path)

    if result.returncode != 0:
        print(f"Failed to update PR: {result.stderr}", file=sys.stderr)
        return 1

    print(f"PR {pr_id} updated.", file=sys.stderr)
    return 0


def _fetch_prs(cmd):
    result = _run_az(cmd)
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def cmd_pr_cache(args):
    cache_dir = os.path.join(os.path.expanduser("~"), ".local", "cache", "gg")
    RESOURCE = "https://app.vssps.visualstudio.com"

    email = _get_git_email()
    if email is None:
        return 1

    queries = [
        f"az repos pr list --creator {shlex.quote(email)} --status all --output json",
        f"az repos pr list --reviewer {shlex.quote(email)} --status all --output json",
        "az repos pr list --status all --output json",
    ]

    seen = set()
    prs = []
    for q in queries:
        for pr in _fetch_prs(q):
            pr_id = pr["pullRequestId"]
            if pr_id not in seen:
                seen.add(pr_id)
                prs.append(pr)

    for pr in prs:
        pr_id = pr["pullRequestId"]
        status = pr.get("status")
        pr_cache_dir = os.path.join(cache_dir, f"pr-{pr_id}")

        if status == "active":
            os.makedirs(pr_cache_dir, exist_ok=True)

            thread_url = pr["url"] + "/threads?api-version=7.1"
            thread_result = _run_az(
                f"az rest --url {shlex.quote(thread_url)} --resource {RESOURCE} --output json"
            )

            thread_active = 0
            thread_total = 0
            if thread_result.returncode == 0:
                with open(os.path.join(pr_cache_dir, "threads.json"), "w") as f:
                    f.write(thread_result.stdout)
                try:
                    thread_data = json.loads(thread_result.stdout)
                    threads = thread_data.get(
                        "value", thread_data if isinstance(thread_data, list) else []
                    )
                    thread_total = len(threads)
                    thread_active = sum(
                        1 for t in threads if t.get("status") == "active"
                    )
                except json.JSONDecodeError:
                    pass

            policy_approved = 0
            policy_running = 0
            policy_total = 0
            policy_result = _run_az(
                f"az repos pr policy list --id {pr_id} --output json"
            )
            if policy_result.returncode == 0:
                with open(os.path.join(pr_cache_dir, "policies.json"), "w") as f:
                    f.write(policy_result.stdout)
                try:
                    policies = json.loads(policy_result.stdout)
                    if isinstance(policies, list):
                        policy_running = sum(
                            1
                            for p in policies
                            if p.get("status") in ("running", "queued")
                        )
                        policy_approved = sum(
                            1 for p in policies if p.get("status") == "approved"
                        )
                        policy_total = len(policies)
                except json.JSONDecodeError:
                    pass

            print(
                f"PR {pr_id}: {thread_active}/{thread_total} threads, {policy_approved}/{policy_running}/{policy_total} policies",
                file=sys.stderr,
            )
        else:
            if os.path.isdir(pr_cache_dir):
                import shutil

                shutil.rmtree(pr_cache_dir)
                print(f"PR {pr_id}: cleaned up", file=sys.stderr)

    return 0


def cmd_pr_show(args):
    pr_id = args.pr_id
    cache_dir = os.path.join(
        os.path.expanduser("~"), ".local", "cache", "gg", f"pr-{pr_id}"
    )

    result = _run_az(f"az repos pr show --id {pr_id} --output json")
    if result.returncode != 0:
        print(f"az command failed: {result.stderr}", file=sys.stderr)
        return 1

    try:
        pr = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Failed to parse PR info.", file=sys.stderr)
        return 1

    pr_id = pr["pullRequestId"]
    title = pr.get("title", "")
    branch = pr.get("sourceRefName", "").removeprefix("refs/heads/")
    creator = pr.get("createdBy", {}).get("uniqueName", "")
    reviewers = pr.get("reviewers") or []

    VOTE_LABELS = {
        10: "approved",
        5: "approved w/suggestions",
        0: "no vote",
        -5: "waiting for author",
        -10: "rejected",
    }

    description = pr.get("description") or ""

    console.print(f"[bold]PR {pr_id}:[/bold] {title}")
    console.print(f"  [dim]Branch:[/dim]  {branch}")
    console.print(f"  [dim]Creator:[/dim] {creator}")
    if description:
        console.print("  [dim]Description:[/dim]")
        for line in description.split("\n"):
            console.print(f"    {line}")

    VOTE_COLORS = {10: "green", 5: "green", 0: "grey62", -5: "yellow", -10: "red"}

    required = [r for r in reviewers if r.get("isRequired")]
    optional = [r for r in reviewers if not r.get("isRequired")]

    def add_reviewers_line(rs, label):
        line = Text("  ")
        line.append(label, style="bold")
        line.append(": ")
        for i, r in enumerate(rs):
            if i > 0:
                line.append("  ")
            name = r.get("uniqueName", "")
            if "\\" in name:
                name = name.split("\\", 1)[1]
            vote = r.get("vote", 0)
            lbl = VOTE_LABELS.get(vote, str(vote))
            color = VOTE_COLORS.get(vote, "")
            line.append(name)
            line.append(f" [{lbl}]", style=color)
        console.print(line)

    if required:
        add_reviewers_line(required, "Required reviewers")
    if optional:
        add_reviewers_line(optional, "Optional reviewers")

    RESOURCE = "https://app.vssps.visualstudio.com"

    threads = []
    threads_path = os.path.join(cache_dir, "threads.json")
    if os.path.isfile(threads_path):
        try:
            with open(threads_path) as f:
                data = json.load(f)
            threads = data.get("value", data if isinstance(data, list) else [])
        except (json.JSONDecodeError, OSError):
            pass
    else:
        thread_url = pr.get("url", "") + "/threads?api-version=7.1"
        if thread_url:
            result = _run_az(
                f"az rest --url {shlex.quote(thread_url)} --resource {RESOURCE} --output json"
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    threads = data.get("value", data if isinstance(data, list) else [])
                except json.JSONDecodeError:
                    pass

    active_threads = [t for t in threads if t.get("status") == "active"]
    if active_threads:
        console.print("  [bold]Active threads:[/bold]")
        for t in active_threads:
            tid = t.get("id", "")
            comments = t.get("comments") or []
            first = comments[0] if comments else {}
            author = first.get("author", {}).get("uniqueName", "")
            content = first.get("content", "")
            first_line = (
                next(
                    (
                        line.strip()
                        for line in content.split("\n")
                        if line.strip() and not line.strip().startswith("[comment]:")
                    ),
                    "",
                )[:80]
                if content
                else ""
            )
            console.print(f"    #{tid} {author}  {first_line}")

    policies = []
    policies_path = os.path.join(cache_dir, "policies.json")
    if os.path.isfile(policies_path):
        try:
            with open(policies_path) as f:
                policies = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    else:
        result = _run_az(f"az repos pr policy list --id {pr_id} --output json")
        if result.returncode == 0:
            try:
                policies = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass

    POLICY_COLORS = {
        "approved": "green",
        "rejected": "red",
        "running": "yellow",
        "queued": "yellow",
        "broken": "red",
        "notApplicable": "grey62",
    }

    if isinstance(policies, list) and policies:
        required = [p for p in policies if p.get("configuration", {}).get("isBlocking")]
        if required:
            console.print("  [bold]Required policies:[/bold]")
            for p in required:
                pid = p.get("configuration", {}).get("id", "")
                cfg = p.get("configuration", {})
                settings = cfg.get("settings", {})
                name = (
                    settings.get("displayName")
                    or settings.get("defaultDisplayName")
                    or settings.get("statusName")
                    or cfg.get("displayName")
                    or cfg.get("type", {}).get("displayName", "")
                )
                status = p.get("status", "")
                color = POLICY_COLORS.get(status, "")
                line = Text(f"    #{pid} {name}  ")
                line.append(status, style=color)
                console.print(line)
                if status == "rejected":
                    ctx = p.get("context") or {}
                    preview = ctx.get("buildOutputPreview") or {}
                    errors = (
                        preview.get("errors") if isinstance(preview, dict) else None
                    )
                    if errors and isinstance(errors, list):
                        for err in errors:
                            msg = (
                                err.get("message", "")
                                if isinstance(err, dict)
                                else str(err)
                            )
                            if msg:
                                console.print(f"      [red]{msg}[/red]")

    return 0


def _is_only_marker_content(content):
    stripped = content.strip()
    if not stripped:
        return True
    for line in stripped.split("\n"):
        line = line.strip()
        if line and not line.startswith("[comment]:"):
            return False
    return True


def _is_system_comment(comment):
    return comment.get("commentType") == "system"


def _is_system_only_thread(thread):
    comments = thread.get("comments") or []
    return bool(comments) and all(_is_system_comment(c) for c in comments)


def _first_display_comment(thread):
    if _is_system_only_thread(thread):
        comments = thread.get("comments") or []
    else:
        comments = [
            comment
            for comment in thread.get("comments") or []
            if not _is_system_comment(comment)
        ]
    for comment in comments:
        content = comment.get("content", "")
        if not _is_only_marker_content(content):
            return comment
    return None


def _is_system_thread(thread):
    return _is_system_only_thread(thread) and thread.get("status") != "active"


def _format_thread_date(value):
    if not value:
        return ""
    return value.replace("T", " ").replace("Z", "")[:16]


def _sanitize_thread_preview(content, max_len=100):
    content = re.sub(r"<[^>]+>", " ", content)
    visible_lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("[comment]:")
    ]
    preview = html.unescape(" ".join(visible_lines))
    preview = re.sub(r"\s+", " ", preview).strip()
    if len(preview) > max_len:
        return preview[: max_len - 1] + "..."
    return preview


def _format_thread_location(thread):
    ctx = thread.get("threadContext") or {}
    file_path = ctx.get("filePath", "")
    if not file_path:
        return ""
    line = (ctx.get("rightFileStart") or {}).get("line")
    if line:
        return f"{file_path}:{line}"
    return file_path


def _format_thread_file_path(thread):
    return (thread.get("threadContext") or {}).get("filePath", "")


def _normalize_thread_file_path(path):
    if not path:
        return ""
    path = str(path)
    base, sep, line = path.rpartition(":")
    if sep and line.isdigit():
        path = base
    return path.lstrip("/")


def _format_threads_for_manage(raw_threads):
    threads = []
    for thread in raw_threads:
        if _is_system_thread(thread):
            continue
        first = _first_display_comment(thread)
        if first is None:
            continue
        file_path = _format_thread_file_path(thread)
        author = first.get("author", {}).get("uniqueName", "")
        if not author and _is_system_comment(first):
            author = "system"
        threads.append(
            {
                "id": thread.get("id", ""),
                "status": thread.get("status", ""),
                "author": author,
                "date": _format_thread_date(first.get("publishedDate", "")),
                "file_path": file_path,
                "location": _format_thread_location(thread),
                "preview": _sanitize_thread_preview(first.get("content", "")),
            }
        )
    return threads


def _raw_threads_from_cache(data):
    if isinstance(data, dict):
        return data.get("value", [])
    if isinstance(data, list):
        return data
    return []


def _threads_for_manage_from_cache(data):
    if isinstance(data, dict) and isinstance(data.get("threads"), list):
        return data["threads"]
    return _format_threads_for_manage(_raw_threads_from_cache(data))


THREAD_RESPONSE_MARKER = "<!-- gg-response-start -->"
THREAD_RESPONSE_PLACEHOLDER = "Write your response here."
NEW_THREAD_COMMENT_MARKER = "<!-- gg-new-thread-comment-start -->"
NEW_THREAD_COMMENT_PLACEHOLDER = "Write your comment here."
THREAD_STATUSES = {"active", "fixed", "wontFix", "closed"}


def _thread_drafts_dir(cache_dir):
    return os.path.join(cache_dir, "threads")


def _thread_draft_path(cache_dir, thread_id):
    return os.path.join(_thread_drafts_dir(cache_dir), f"thread-{thread_id}.md")


def _new_thread_draft_path(cache_dir, draft_id):
    return os.path.join(_thread_drafts_dir(cache_dir), f"{draft_id}.md")


def _read_marker_content(path, marker, placeholder):
    try:
        with open(path) as f:
            content = f.read()
    except OSError:
        return ""
    idx = content.find(marker)
    if idx == -1:
        return ""
    value = content[idx + len(marker) :].strip()
    if not value or value == placeholder:
        return ""
    return value


def _read_thread_response(thread_file):
    return _read_marker_content(
        thread_file, THREAD_RESPONSE_MARKER, THREAD_RESPONSE_PLACEHOLDER
    )


def _read_new_thread_comment(thread_file):
    return _read_marker_content(
        thread_file, NEW_THREAD_COMMENT_MARKER, NEW_THREAD_COMMENT_PLACEHOLDER
    )


def _read_frontmatter(path):
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    if not lines or lines[0] != "---":
        return {}
    result = {}
    for line in lines[1:]:
        if line == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            result[key.strip()] = value.strip()
    return result


def _replace_frontmatter_value(path, key, value):
    with open(path) as f:
        lines = f.read().splitlines()
    if not lines or lines[0] != "---":
        return False

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line == "---":
            end = i
            break
    if end is None:
        return False

    replaced = False
    for i in range(1, end):
        current_key, sep, _ = lines[i].partition(":")
        if sep and current_key.strip() == key:
            lines[i] = f"{key}: {value}"
            replaced = True
            break
    if not replaced:
        lines.insert(end, f"{key}: {value}")

    with open(path, "w") as f:
        f.write("\n".join(lines))
        f.write("\n")
    return True


def _pending_thread_responses(cache_dir):
    drafts_dir = _thread_drafts_dir(cache_dir)
    if not os.path.isdir(drafts_dir):
        return {}
    result = {}
    for name in sorted(os.listdir(drafts_dir)):
        match = re.fullmatch(r"thread-(\d+)\.md", name)
        if not match:
            continue
        thread_id = match.group(1)
        path = os.path.join(drafts_dir, name)
        response = _read_thread_response(path)
        if response:
            result[thread_id] = {"path": path, "response": response}
    return result


def _thread_status_by_id(cache_dir):
    result = {}
    for thread in _load_raw_threads(cache_dir):
        thread_id = str(thread.get("id", ""))
        if thread_id:
            result[thread_id] = thread.get("status", "")
    return result


def _pending_thread_status_changes(cache_dir):
    drafts_dir = _thread_drafts_dir(cache_dir)
    if not os.path.isdir(drafts_dir):
        return {}
    original_status = _thread_status_by_id(cache_dir)
    result = {}
    for name in sorted(os.listdir(drafts_dir)):
        match = re.fullmatch(r"thread-(\d+)\.md", name)
        if not match:
            continue
        thread_id = match.group(1)
        path = os.path.join(drafts_dir, name)
        meta = _read_frontmatter(path)
        status = meta.get("status", "")
        if status not in THREAD_STATUSES:
            continue
        if original_status.get(thread_id) and status != original_status.get(thread_id):
            result[thread_id] = {"path": path, "status": status}
    return result


def _pending_new_thread_drafts(cache_dir):
    drafts_dir = _thread_drafts_dir(cache_dir)
    if not os.path.isdir(drafts_dir):
        return {}
    result = {}
    for name in sorted(os.listdir(drafts_dir)):
        match = re.fullmatch(r"(new-[^.]+)\.md", name)
        if not match:
            continue
        draft_id = match.group(1)
        path = os.path.join(drafts_dir, name)
        comment = _read_new_thread_comment(path)
        if not comment:
            continue
        meta = _read_frontmatter(path)
        result[draft_id] = {
            "path": path,
            "comment": comment,
            "file_path": meta.get("file_path", ""),
            "side": meta.get("side", ""),
            "line": meta.get("line", ""),
            "status": meta.get("status", "active"),
        }
    return result


def _new_thread_drafts_for_manage(cache_dir):
    drafts_dir = _thread_drafts_dir(cache_dir)
    if not os.path.isdir(drafts_dir):
        return []
    result = []
    for name in sorted(os.listdir(drafts_dir)):
        match = re.fullmatch(r"(new-[^.]+)\.md", name)
        if not match:
            continue
        draft_id = match.group(1)
        path = os.path.join(drafts_dir, name)
        meta = _read_frontmatter(path)
        file_path = meta.get("file_path", "")
        line = meta.get("line", "")
        location = file_path
        if location and line:
            location = f"{location}:{line}"
        result.append(
            {
                "id": draft_id,
                "path": path,
                "location": location,
                "has_comment": bool(_read_new_thread_comment(path)),
            }
        )
    return result


def _get_thread_counts_by_file(threads):
    counts = {}
    for thread in threads:
        file_path = _normalize_thread_file_path(
            thread.get("file_path") or thread.get("location", "")
        )
        if not file_path:
            continue
        entry = counts.setdefault(file_path, {"active": 0, "total": 0})
        entry["total"] += 1
        if thread.get("status") == "active":
            entry["active"] += 1
    return counts


def _format_change_line(change_file, thread_counts=None):
    line = f"{change_file['status']}  {change_file['filename']}"
    counts = []
    if change_file.get("added", 0) > 0:
        counts.append(f"+{change_file['added']}")
    if change_file.get("deleted", 0) > 0:
        counts.append(f"-{change_file['deleted']}")
    if counts:
        line += "  " + " ".join(counts)
    if thread_counts:
        thread_count = thread_counts.get(change_file["filename"])
        if thread_count and thread_count.get("total", 0) > 0:
            line += (
                f" [{thread_count.get('active', 0)}/{thread_count['total']} threads]"
            )
    return line


def _append_manage_threads(lines, threads):
    lines.append("# Threads")
    lines.append("")
    for thread in threads:
        status = thread.get("status", "")
        author = thread.get("author", "")
        location = thread.get("location", "")
        date = thread.get("date", "")
        suffix_parts = []
        if author:
            suffix_parts.append(f"by {author}")
        if location:
            suffix_parts.append(location)
        if date:
            suffix_parts.append(date)
        suffix = f" {' '.join(suffix_parts)}" if suffix_parts else ""
        lines.append(f"- [{thread.get('id', '')}] (**{status}**){suffix}")
        preview = thread.get("preview", "")
        if preview:
            lines.append(f"  {preview}")
    lines.append("")


def _policy_name(policy):
    cfg = policy.get("configuration", {})
    settings = cfg.get("settings", {})
    return (
        settings.get("displayName")
        or settings.get("defaultDisplayName")
        or settings.get("statusName")
        or cfg.get("displayName")
        or cfg.get("type", {}).get("displayName", "")
    )


def _policy_errors(policy):
    ctx = policy.get("context") or {}
    preview = ctx.get("buildOutputPreview") or {}
    errors = preview.get("errors") if isinstance(preview, dict) else None
    if not isinstance(errors, list):
        return []
    result = []
    for err in errors:
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        if msg:
            result.append(msg)
    return result


def _policy_is_expired(policy):
    return bool(policy.get("isExpired") or (policy.get("context") or {}).get("isExpired"))


def _format_policies_for_manage(raw_policies):
    if not isinstance(raw_policies, list):
        return []
    policies = []
    for policy in raw_policies:
        cfg = policy.get("configuration", {})
        if not cfg.get("isBlocking"):
            continue
        policies.append(
            {
                "id": cfg.get("id", ""),
                "evaluation_id": policy.get("evaluationId", ""),
                "name": _policy_name(policy),
                "status": "expired" if _policy_is_expired(policy) else policy.get("status", ""),
                "errors": _policy_errors(policy),
            }
        )
    return policies


def _append_manage_policies(lines, policies):
    lines.append("# Policies")
    lines.append("")
    for policy in policies:
        lines.append(
            f"- [{policy.get('id', '')}] {policy.get('name', '')} "
            f"- **{policy.get('status', '')}**"
        )
        for error in policy.get("errors", []):
            error_lines = str(error).splitlines() or [""]
            for error_line in error_lines:
                lines.append(f"  {error_line}")
    lines.append("")


def _regenerate_thread_file(
    thread_file, thread_url, thread_id, resource, old_content, new_status
):
    import shlex

    hunk_block = ""
    if "```diff" in old_content:
        hstart = old_content.find("```diff")
        hend = old_content.find("```", hstart + 3)
        if hend != -1:
            hunk_block = old_content[hstart : hend + 3]

    result = _run_az(
        f"az rest --url {shlex.quote(thread_url)} --resource {resource} --output json"
    )
    if result.returncode != 0:
        return

    data = json.loads(result.stdout)
    comments = data.get("comments") or []
    status = data.get("status", new_status or "")

    with open(thread_file, "w") as f:
        f.write("---\n")
        f.write(f"id: {thread_id}\n")
        first = comments[0] if comments else {}
        f.write(f"author: {first.get('author', {}).get('uniqueName', '')}\n")
        ctx = data.get("threadContext") or {}
        file_path = ctx.get("filePath", "")
        if file_path:
            location_line = ctx.get("rightFileStart", {}).get("line")
            loc = f"{file_path}:{location_line}" if location_line else file_path
            f.write(f"location: {loc}\n")
        f.write(f"status: {status}\n")
        f.write("---\n\n")
        if hunk_block:
            f.write(hunk_block + "\n\n")
        for c in comments:
            author = c.get("author", {}).get("uniqueName", "")
            content = c.get("content", "")
            if content and not _is_only_marker_content(content):
                f.write(f"**{author}:**\n\n{content}\n\n---\n\n")
        f.write("\n**Your response:**\n\n")
        f.write(
            "Write your response here. To update thread status, change the `status` field "
        )
        f.write("in the frontmatter above.\n")
        f.write("Valid statuses: active, fixed, wontFix, closed\n")
        f.write("Then save the file and run `:PR post` to submit.\n")
    print(f"Thread file regenerated with {len(comments)} comments.", file=sys.stderr)


def _get_file_hunks(full_diff, file_path, start_line=None, end_line=None):
    import re

    rel_path = file_path.lstrip("/")
    lines = full_diff.split("\n")

    file_start = None
    for i, line in enumerate(lines):
        if (
            line.startswith("diff --git ")
            and f" a/{rel_path}" in line
            and f" b/{rel_path}" in line
        ):
            file_start = i
            break

    if file_start is None:
        return ""

    file_end = len(lines)
    for i in range(file_start + 1, len(lines)):
        if lines[i].startswith("diff --git "):
            file_end = i
            break

    file_lines = lines[file_start:file_end]
    if not file_lines:
        return ""

    if start_line is None or end_line is None:
        return "\n".join(file_lines)

    hunk_header = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    header = []
    hunks = []
    current_hunk = None

    for line in file_lines:
        m = hunk_header.match(line)
        if m:
            if current_hunk is not None:
                hunks.append(current_hunk)
            new_start = int(m.group(1))
            new_count = int(m.group(2)) if m.group(2) else 1
            current_hunk = {
                "start": new_start,
                "end": new_start + new_count - 1,
                "lines": [line],
            }
        elif current_hunk is not None:
            current_hunk["lines"].append(line)
        else:
            header.append(line)

    if current_hunk is not None:
        hunks.append(current_hunk)

    matching = [
        h for h in hunks if not (h["end"] < start_line or h["start"] > end_line)
    ]

    if not matching:
        return ""

    result = list(header)
    for h in matching:
        result.extend(h["lines"])

    return "\n".join(result)


def cmd_pr_review(args):
    pr_id = args.pr_id

    print(f"Fetching PR {pr_id} info...", file=sys.stderr)
    result = _run_az(f"az repos pr show --id {pr_id} --output json")
    if result.returncode != 0:
        print(f"az command failed: {result.stderr}", file=sys.stderr)
        return 1

    try:
        pr = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Failed to parse PR info.", file=sys.stderr)
        return 1

    title = pr.get("title", "")
    description = pr.get("description") or ""
    branch = pr.get("sourceRefName", "").removeprefix("refs/heads/")
    is_draft = pr.get("isDraft", False)
    auto_complete = pr.get("autoCompleteSetBy") is not None

    print(f"PR {pr_id}: {title}", file=sys.stderr)
    print(f"  Branch: {branch}", file=sys.stderr)
    print(
        f"  Status: {'draft' if is_draft else 'auto-complete' if auto_complete else 'active'}",
        file=sys.stderr,
    )

    if branch:
        print(f"Fetching origin/{branch}...", file=sys.stderr)
        fetch_result = run(["git", "fetch", "origin", branch])
        if fetch_result.returncode != 0:
            print(
                f"  Warning: fetch failed: {fetch_result.stderr.strip()}",
                file=sys.stderr,
            )
        else:
            print(f"  Fetched origin/{branch}", file=sys.stderr)

    tmpdir = tempfile.mkdtemp(prefix=f"pr-review-{pr_id}-")
    print(f"  Temp dir: {tmpdir}", file=sys.stderr)

    summary_path = os.path.join(tmpdir, "summary.md")
    with open(summary_path, "w") as f:
        f.write(f"{title}\n")
        if is_draft:
            f.write("draft\n")
        elif auto_complete:
            f.write("auto-complete\n")
        else:
            f.write("active\n")
        if description:
            f.write(f"{description}\n")
    print("  Created summary.md", file=sys.stderr)

    changes_path = os.path.join(tmpdir, "changes.diff")
    full_diff = ""
    if branch:
        for base in ("origin/master", "origin/main"):
            tip = f"origin/{branch}"
            print(f"  Generating diff: git diff {base}...{tip}", file=sys.stderr)
            diff_result = run(["git", "diff", f"{base}...{tip}"])
            if diff_result.returncode == 0:
                full_diff = diff_result.stdout
                print(
                    f"  Diff generated against {base} ({len(full_diff)} bytes)",
                    file=sys.stderr,
                )
                break
            else:
                stderr = diff_result.stderr.strip()
                if stderr:
                    print(f"  {base} failed: {stderr}", file=sys.stderr)
        if full_diff:
            with open(changes_path, "w") as f:
                f.write(full_diff)
            print(f"  Created changes.diff ({len(full_diff)} bytes)", file=sys.stderr)
        else:
            print(
                "  Warning: could not generate diff (no origin/master or origin/main found)",
                file=sys.stderr,
            )

    policies_path = os.path.join(tmpdir, "policies.md")
    print("  Fetching policies...", file=sys.stderr)
    policy_result = _run_az(f"az repos pr policy list --id {pr_id} --output json")
    policies = []
    if policy_result.returncode == 0:
        try:
            policies = json.loads(policy_result.stdout)
            print(
                f"  Fetched {len(policies) if isinstance(policies, list) else 0} policies",
                file=sys.stderr,
            )
        except json.JSONDecodeError:
            print("  Warning: failed to parse policies JSON", file=sys.stderr)
    else:
        print(
            f"  Warning: policy fetch failed: {policy_result.stderr.strip()}",
            file=sys.stderr,
        )

    with open(policies_path, "w") as f:
        if isinstance(policies, list) and policies:
            for p in policies:
                cfg = p.get("configuration", {})
                settings = cfg.get("settings", {})
                name = (
                    settings.get("displayName")
                    or settings.get("defaultDisplayName")
                    or settings.get("statusName")
                    or cfg.get("displayName")
                    or cfg.get("type", {}).get("displayName", "")
                )
                status = p.get("status", "")
                is_blocking = cfg.get("isBlocking", False)

                f.write(f"- **{name}**  \n")
                f.write(f"  Status: {status}")
                if is_blocking:
                    f.write(" (blocking)")
                f.write("\n")
                if status == "rejected":
                    ctx = p.get("context") or {}
                    preview = ctx.get("buildOutputPreview") or {}
                    errors = (
                        preview.get("errors") if isinstance(preview, dict) else None
                    )
                    if errors and isinstance(errors, list):
                        for err in errors:
                            msg = (
                                err.get("message", "")
                                if isinstance(err, dict)
                                else str(err)
                            )
                            if msg:
                                f.write(f"  - Error: {msg}\n")
                f.write("\n")
        else:
            f.write("No policies found.\n")
    print("  Created policies.md", file=sys.stderr)

    RESOURCE = "https://app.vssps.visualstudio.com"
    thread_url = pr.get("url", "") + "/threads?api-version=7.1"
    threads = []
    if thread_url:
        print("  Fetching comment threads...", file=sys.stderr)
        thread_result = _run_az(
            f"az rest --url {shlex.quote(thread_url)} --resource {RESOURCE} --output json"
        )
        if thread_result.returncode == 0:
            try:
                data = json.loads(thread_result.stdout)
                threads = data.get("value", data if isinstance(data, list) else [])
                print(f"  Fetched {len(threads)} threads total", file=sys.stderr)
            except json.JSONDecodeError:
                print("  Warning: failed to parse threads JSON", file=sys.stderr)
        else:
            print(
                f"  Warning: thread fetch failed: {thread_result.stderr.strip()}",
                file=sys.stderr,
            )

    print(f"  Writing {len(threads)} thread files...", file=sys.stderr)
    for t in threads:
        tcomments = t.get("comments") or []
        if tcomments and all(c.get("commentType") == "system" for c in tcomments):
            continue
        tid = t.get("id", "")

        thread_path = os.path.join(tmpdir, f"thread-{tid}.md")
        with open(thread_path, "w") as f:
            thread_context = t.get("threadContext") or {}
            file_path = thread_context.get("filePath", "")
            first = tcomments[0] if tcomments else {}
            first_author = first.get("author", {}).get("uniqueName", "")
            location_line = thread_context.get("rightFileStart", {}).get("line")

            f.write("---\n")
            f.write(f"id: {tid}\n")
            f.write(f"author: {first_author}\n")
            if file_path:
                loc = file_path
                if location_line:
                    loc = f"{loc}:{location_line}"
                f.write(f"location: {loc}\n")
            f.write(f"status: {t.get('status', '')}\n")
            f.write("---\n\n")

            if file_path:
                start = thread_context.get("rightFileStart", {}).get("line")
                end = thread_context.get("rightFileEnd", {}).get("line")
                hunk = _get_file_hunks(full_diff, file_path, start, end)
                if hunk:
                    f.write(f"```diff\n{hunk}\n```\n\n")

            for c in tcomments:
                author = c.get("author", {}).get("uniqueName", "")
                content = c.get("content", "")
                if content and not _is_only_marker_content(content):
                    f.write(f"**{author}:**\n\n{content}\n\n---\n\n")

            f.write("\n**Your response:**\n\n")
            f.write(
                "Write your response here. To update thread status, change the `status` field "
            )
            f.write("in the frontmatter above.\n")
            f.write("Valid statuses: active, fixed, wontFix, closed\n")
            f.write("Then save the file and run `:PR post` to submit.\n")

    lua_code = f"""\
local pr_id = {pr_id}
vim.api.nvim_create_user_command('PR', function(opts)
  if opts.args == 'post' then
    vim.cmd('write')
    local filepath = vim.fn.expand('%:p')
    local name = vim.fn.expand('%:t:r')
    vim.notify('Name: ' .. name, vim.log.levels.DEBUG)
    local _, last = name:find('thread%-')
    local thread_id = nil
    if last then
      thread_id = name:sub(last + 1)
    end
    if thread_id then
      local result = vim.fn.system({{'gg', 'pr', 'respond', tostring(pr_id), thread_id, filepath}})
      if vim.v.shell_error == 0 then
        vim.cmd('edit!')
        vim.notify('Response posted to thread ' .. thread_id, vim.log.levels.INFO)
      else
        vim.notify('Failed: ' .. result, vim.log.levels.ERROR)
      end
    else
      vim.notify('Not a thread buffer: ' .. filepath, vim.log.levels.WARN)
    end
  end
end, {{nargs = 1}})
"""
    lua_path = os.path.join(tmpdir, "review.lua")
    with open(lua_path, "w") as f:
        f.write(lua_code)

    file_paths = [summary_path]
    if os.path.isfile(changes_path):
        file_paths.append(changes_path)
    if os.path.isfile(policies_path):
        file_paths.append(policies_path)
    thread_files = sorted(
        os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.startswith("thread-")
    )
    file_paths.extend(thread_files)
    print(f"Opening {len(file_paths)} files in nvim...", file=sys.stderr)
    subprocess.run(["nvim"] + file_paths + ["-c", f"luafile {shlex.quote(lua_path)}"])

    import shutil

    shutil.rmtree(tmpdir)

    return 0


def cmd_pr_respond(args):
    pr_id = args.pr_id
    thread_id = args.thread_id
    thread_file = args.thread_file

    with open(thread_file, "r") as f:
        content = f.read()

    pr_result = _run_az(f"az repos pr show --id {pr_id} --output json")
    if pr_result.returncode != 0:
        print(f"Failed to get PR info: {pr_result.stderr}", file=sys.stderr)
        return 1

    pr = json.loads(pr_result.stdout)
    pr_url = pr.get("url", "")
    RESOURCE = "https://app.vssps.visualstudio.com"
    thread_url = f"{pr_url}/threads/{thread_id}?api-version=7.1"

    lines = content.split("\n")
    first = None
    second = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if first is None:
                first = i
            elif second is None:
                second = i
                break

    new_status = None
    if first is not None and second is not None:
        for line in lines[first + 1 : second]:
            if ":" in line:
                key, value = line.split(":", 1)
                if key.strip() == "status":
                    new_status = value.strip()
                    break

    if new_status:
        thread_result = _run_az(
            f"az rest --url {shlex.quote(thread_url)} --resource {RESOURCE} --output json"
        )
        if thread_result.returncode == 0:
            current_status = json.loads(thread_result.stdout).get("status", "")
            if new_status != current_status:
                fd, body_path = tempfile.mkstemp(suffix=".json")
                with os.fdopen(fd, "w") as f:
                    json.dump({"status": new_status}, f)
                patch_cmd = (
                    f"az rest --method PATCH --url {shlex.quote(thread_url)} "
                    f"--body @{shlex.quote(body_path)} "
                    f"--headers Content-Type=application/json "
                    f"--resource {RESOURCE}"
                )
                patch_result = _run_az(patch_cmd)
                os.unlink(body_path)
                if patch_result.returncode == 0:
                    print(f"Thread status updated to {new_status}.", file=sys.stderr)
                else:
                    print(
                        f"Warning: failed to update status: {patch_result.stderr.strip()}",
                        file=sys.stderr,
                    )

    marker = "**Your response:**"
    idx = content.rfind(marker)
    if idx == -1:
        print("No response section found in thread file.", file=sys.stderr)
        return 1

    response = content[idx + len(marker) :].strip()

    placeholder = (
        "Write your response here. To update thread status, change the `status` field "
        "in the frontmatter above.\n"
        "Valid statuses: active, fixed, wontFix, closed\n"
        "Then save the file and run `:PR post` to submit."
    )

    if not response or response == placeholder:
        print("No changes detected. Response not posted.", file=sys.stderr)
        if new_status:
            print("Regenerating to reflect status change.", file=sys.stderr)
            _regenerate_thread_file(
                thread_file, thread_url, thread_id, RESOURCE, content, new_status
            )
        return 0

    comment_url = f"{pr_url}/threads/{thread_id}/comments?api-version=7.1"
    fd, body_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"content": response, "commentType": "text"}, f)

    cmd = (
        f"az rest --method POST --url {shlex.quote(comment_url)} "
        f"--body @{shlex.quote(body_path)} "
        f"--headers Content-Type=application/json "
        f"--resource {RESOURCE}"
    )
    result = _run_az(cmd)
    os.unlink(body_path)

    if result.returncode != 0:
        print(f"Failed to post response: {result.stderr}", file=sys.stderr)
        return 1

    print(f"Response posted to thread {thread_id}.", file=sys.stderr)
    _regenerate_thread_file(
        thread_file, thread_url, thread_id, RESOURCE, content, new_status
    )

    return 0


def _get_cache_dir(pr_id):
    return os.path.join(os.path.expanduser("~"), ".cache", "gg", f"pr-{pr_id}")


PR_STATUSES = ["abandoned", "draft", "active", "auto-complete", "completed"]
VOTE_ACTIONS = {
    "approve": {"vote": 10, "label": "approve"},
    "approve with suggestion": {"vote": 5, "label": "approve with suggestion"},
    "reset": {"vote": 0, "label": "reset"},
    "wait for author": {"vote": -5, "label": "wait for author"},
    "reject": {"vote": -10, "label": "reject"},
    "abstain": {"remove": True, "label": "abstain"},
}


def _get_pr_status_label(pr):
    ado_status = pr.get("status", "active")
    if ado_status == "abandoned":
        return "abandoned"
    if ado_status == "completed":
        return "completed"
    if pr.get("isDraft", False):
        return "draft"
    if pr.get("autoCompleteSetBy") is not None:
        return "auto-complete"
    return "active"


def _status_to_api_body(label):
    return {
        "abandoned": {"status": "abandoned"},
        "completed": {"status": "completed"},
        "draft": {"isDraft": True},
        "active": {"isDraft": False},
        "auto-complete": {"isDraft": False},
    }.get(label, {})


def _get_current_user_email():
    result = _run_az("az account show --query user.name -o tsv")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return _get_git_email()


def _ado_org_from_pr_url(pr):
    match = re.match(r"https://dev\.azure\.com/([^/]+)/", pr.get("url", ""))
    if match:
        return match.group(1)
    match = re.match(r"https://([^/.]+)\.visualstudio\.com/", pr.get("url", ""))
    if match:
        return match.group(1)
    return ""


def _ado_project_from_pr_url(pr):
    match = re.match(r"https://dev\.azure\.com/[^/]+/([^/]+)/", pr.get("url", ""))
    if match:
        return match.group(1)
    match = re.match(r"https://[^/.]+\.visualstudio\.com/([^/]+)/", pr.get("url", ""))
    if match:
        return match.group(1)
    return ""


def _reviewer_matches_email(reviewer, email):
    email = email.lower()
    for key in ("uniqueName", "mailAddress", "principalName"):
        value = reviewer.get(key)
        if isinstance(value, str) and value.lower() == email:
            return True
    return False


def _lookup_ado_identity_id(pr, email):
    org = _ado_org_from_pr_url(pr)
    if not org:
        return ""
    url = f"https://vssps.dev.azure.com/{org}/_apis/graph/users?api-version=7.1-preview.1"
    result = _run_az(f"az rest --method GET --url {shlex.quote(url)} --resource {_RESOURCE}")
    if result.returncode != 0:
        return ""
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""

    for user in data.get("value", []):
        if not _reviewer_matches_email(user, email):
            continue
        descriptor = user.get("descriptor", "")
        if descriptor:
            storage_url = (
                f"https://vssps.dev.azure.com/{org}/_apis/graph/storagekeys/"
                f"{quote(descriptor, safe='')}?api-version=7.1-preview.1"
            )
            storage_result = _run_az(
                f"az rest --method GET --url {shlex.quote(storage_url)} --resource {_RESOURCE}"
            )
            if storage_result.returncode == 0:
                try:
                    storage_data = json.loads(storage_result.stdout)
                except json.JSONDecodeError:
                    storage_data = {}
                if storage_data.get("value"):
                    return storage_data["value"]
        return user.get("originId") or user.get("id") or ""
    return ""


def _resolve_current_reviewer_id(pr):
    email = _get_current_user_email()
    if not email:
        return "", ""
    for reviewer in pr.get("reviewers") or []:
        if _reviewer_matches_email(reviewer, email):
            return email, reviewer.get("id") or reviewer.get("uniqueName") or email
    identity_id = _lookup_ado_identity_id(pr, email)
    return email, identity_id


def _update_reviewer_vote(pr, action):
    email, reviewer_id = _resolve_current_reviewer_id(pr)
    if not reviewer_id:
        return subprocess.CompletedProcess(
            "get current user",
            1,
            stdout="",
            stderr="failed to determine current Azure DevOps reviewer identity",
        )

    api_url = f"{pr['url']}/reviewers/{quote(reviewer_id, safe='')}?api-version=7.1"
    if VOTE_ACTIONS[action].get("remove"):
        return _run_az(
            f"az rest --method DELETE --url {shlex.quote(api_url)} --resource {_RESOURCE}"
        )

    fd, body_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"vote": VOTE_ACTIONS[action]["vote"]}, f)
    try:
        return _run_az(
            f"az rest --method PUT --url {shlex.quote(api_url)} "
            f"--body @{shlex.quote(body_path)} "
            f"--headers Content-Type=application/json "
            f"--resource {_RESOURCE}"
        )
    finally:
        os.unlink(body_path)


def _apply_vote_to_cached_pr(pr, action):
    email = _get_current_user_email()
    if not email:
        return
    reviewers = pr.setdefault("reviewers", [])
    if VOTE_ACTIONS[action].get("remove"):
        pr["reviewers"] = [
            reviewer
            for reviewer in reviewers
            if reviewer.get("uniqueName", "").lower() != email.lower()
        ]
        return
    for reviewer in reviewers:
        if reviewer.get("uniqueName", "").lower() == email.lower():
            reviewer["vote"] = VOTE_ACTIONS[action]["vote"]
            return
    reviewers.append({"uniqueName": email, "vote": VOTE_ACTIONS[action]["vote"]})


def _format_manage_reviewer_lines(pr):
    reviewers = pr.get("reviewers") or []

    VOTE_LABELS = {
        10: "approved",
        5: "approved w/suggestions",
        0: "no vote",
        -5: "wait for author",
        -10: "rejected",
    }

    lines = ["# Reviewers", ""]
    for r in sorted(reviewers, key=lambda x: not x.get("isRequired", False)):
        name = r.get("uniqueName", "")
        if "\\" in name:
            name = name.split("\\", 1)[1]
        vote = r.get("vote", 0)
        lbl = VOTE_LABELS.get(vote, str(vote))
        required = " (required)" if r.get("isRequired") else ""
        lines.append(f"- {name}{required} - **{lbl}**")
    lines.append("")
    return lines


def _format_manage_content(pr, cache_dir=None):
    pr_id = pr["pullRequestId"]
    title = pr.get("title", "")
    description = pr.get("description") or ""
    branch = pr.get("sourceRefName", "").removeprefix("refs/heads/")
    target = pr.get("targetRefName", "").removeprefix("refs/heads/")
    creator = pr.get("createdBy", {}).get("uniqueName", "")
    lines = []
    lines.append(f"id: {pr_id}")
    lines.append(f"status: {_get_pr_status_label(pr)}")
    lines.append(f"source: {branch}")
    lines.append(f"target: {target}")
    lines.append(f"created: {creator}")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    if description:
        lines.append(description)
        lines.append("")
    lines.extend(_format_manage_reviewer_lines(pr))

    threads = []
    if cache_dir:
        threads_path = os.path.join(cache_dir, "threads.json")
        if os.path.isfile(threads_path):
            try:
                with open(threads_path) as f:
                    data = json.load(f)
                threads = _threads_for_manage_from_cache(data)
            except (json.JSONDecodeError, OSError):
                pass
    _append_manage_threads(lines, threads)
    thread_counts = _get_thread_counts_by_file(threads)

    lines.append("# Changes")
    lines.append("")

    if cache_dir:
        changes_path = os.path.join(cache_dir, "changes.json")
        if os.path.isfile(changes_path):
            try:
                with open(changes_path) as f:
                    changes = json.load(f)
                for cf in changes.get("files", []):
                    lines.append(_format_change_line(cf, thread_counts))
                if changes.get("total_files", 0) > 0:
                    lines.append("")
                    lines.append(
                        f"{changes['total_files']} files changed +{changes['total_added']} -{changes['total_deleted']}"
                    )
                lines.append("")
            except (json.JSONDecodeError, OSError):
                pass

    policies = []
    if cache_dir:
        policies_path = os.path.join(cache_dir, "policies.json")
        if os.path.isfile(policies_path):
            try:
                with open(policies_path) as f:
                    data = json.load(f)
                policies = _format_policies_for_manage(data)
            except (json.JSONDecodeError, OSError):
                pass
    _append_manage_policies(lines, policies)

    return "\n".join(lines)


def _get_manage_lua(pr_id, manage_path, cache_dir):
    return (
        "local pr_id = {pr_id}\n"
        "local manage_path = [[{manage_path}]]\n"
        "local cache_dir = [[{cache_dir}]]\n"
        "local ns = vim.api.nvim_create_namespace('pr_manage')\n"
        "\n"
        "vim.bo.bufhidden = 'hide'\n"
        "vim.bo.filetype = 'markdown'\n"
        "vim.bo.modifiable = false\n"
        "\n"
        "if not vim.g.gg_pr_manage_init then\n"
        "  vim.g.gg_pr_manage_init = true\n"
        "  vim.api.nvim_set_hl(0, 'ApprovedHL', {{ fg = '#00ff00' }})\n"
        "  vim.api.nvim_set_hl(0, 'WaitForAuthorHL', {{ fg = '#ff0000' }})\n"
        "  vim.api.nvim_set_hl(0, 'NoVoteHL', {{ fg = '#808080' }})\n"
        "  vim.api.nvim_set_hl(0, 'ChangesModifiedHL', {{ fg = '#ffff00' }})\n"
        "  vim.api.nvim_set_hl(0, 'ChangesAddedHL', {{ fg = '#00ff00' }})\n"
        "  vim.api.nvim_set_hl(0, 'ChangesDeletedHL', {{ fg = '#ff0000' }})\n"
        "  vim.api.nvim_set_hl(0, 'ChangesAddHL', {{ fg = '#00ff00' }})\n"
        "  vim.api.nvim_set_hl(0, 'ChangesDelHL', {{ fg = '#ff0000' }})\n"
        "  vim.api.nvim_set_hl(0, 'ThreadFixedHL', {{ fg = '#00ff00' }})\n"
        "  vim.api.nvim_set_hl(0, 'ThreadActiveHL', {{ fg = '#ffff00' }})\n"
        "  vim.api.nvim_set_hl(0, 'DiffThreadHL', {{ fg = '#00ffff' }})\n"
        "  vim.api.nvim_set_hl(0, 'PolicyQueuedHL', {{ fg = '#ffff00' }})\n"
        "  vim.api.nvim_set_hl(0, 'PolicyRunningHL', {{ fg = '#ffff00' }})\n"
        "  vim.api.nvim_set_hl(0, 'PolicyRejectedHL', {{ fg = '#ff0000' }})\n"
        "  vim.api.nvim_set_hl(0, 'PolicyExpiredHL', {{ fg = '#ff0000' }})\n"
        "  vim.api.nvim_set_hl(0, 'PolicyNotApplicableHL', {{ fg = '#808080' }})\n"
        "  vim.fn.matchadd('ApprovedHL', [[\\*\\*approved\\*\\*]])\n"
        "  vim.fn.matchadd('WaitForAuthorHL', [[\\*\\*wait for author\\*\\*]])\n"
        "  vim.fn.matchadd('NoVoteHL', [[\\*\\*no vote\\*\\*]])\n"
        "  vim.fn.matchadd('ThreadFixedHL', [[\\*\\*fixed\\*\\*]])\n"
        "  vim.fn.matchadd('ThreadActiveHL', [[\\*\\*active\\*\\*]])\n"
        "  vim.fn.matchadd('PolicyQueuedHL', [[\\*\\*queued\\*\\*]])\n"
        "  vim.fn.matchadd('PolicyRunningHL', [[\\*\\*running\\*\\*]])\n"
        "  vim.fn.matchadd('PolicyRejectedHL', [[\\*\\*rejected\\*\\*]])\n"
        "  vim.fn.matchadd('PolicyExpiredHL', [[\\*\\*expired\\*\\*]])\n"
        "  vim.fn.matchadd('PolicyNotApplicableHL', [[\\*\\*notApplicable\\*\\*]])\n"
        "end\n"
        "\n"
        "local ACTIONS = {{\n"
        "  {{ label = 'Status: abandoned', kind = 'status', value = 'abandoned' }},\n"
        "  {{ label = 'Status: draft', kind = 'status', value = 'draft' }},\n"
        "  {{ label = 'Status: active', kind = 'status', value = 'active' }},\n"
        "  {{ label = 'Status: complete', kind = 'status', value = 'completed' }},\n"
        "  {{ label = 'Status: auto-complete', kind = 'status', value = 'auto-complete' }},\n"
        "  {{ label = 'Vote: approve', kind = 'vote', value = 'approve' }},\n"
        "  {{ label = 'Vote: approve with suggestion', kind = 'vote', value = 'approve with suggestion' }},\n"
        "  {{ label = 'Vote: reset', kind = 'vote', value = 'reset' }},\n"
        "  {{ label = 'Vote: wait for author', kind = 'vote', value = 'wait for author' }},\n"
        "  {{ label = 'Vote: reject', kind = 'vote', value = 'reject' }},\n"
        "  {{ label = 'Vote: abstain', kind = 'vote', value = 'abstain' }},\n"
        "}}\n"
        "local manage_has_pending_changes = false\n"
        "local pending_thread_ids = {{}}\n"
        "local pending_thread_status_ids = {{}}\n"
        "local pending_thread_statuses = {{}}\n"
        "local pending_new_threads = {{}}\n"
        "\n"
        "local function apply_manage_modified(buf)\n"
        "  buf = buf or vim.api.nvim_get_current_buf()\n"
        "  vim.bo[buf].modified = manage_has_pending_changes\n"
        "end\n"
        "\n"
        "local function set_pending_thread_ids(ids)\n"
        "  pending_thread_ids = {{}}\n"
        "  for _, id in ipairs(ids or {{}}) do\n"
        "    pending_thread_ids[tostring(id)] = true\n"
        "  end\n"
        "end\n"
        "\n"
        "local function set_pending_thread_status_ids(ids)\n"
        "  pending_thread_status_ids = {{}}\n"
        "  for _, id in ipairs(ids or {{}}) do\n"
        "    pending_thread_status_ids[tostring(id)] = true\n"
        "  end\n"
        "end\n"
        "\n"
        "local function set_pending_thread_statuses(statuses)\n"
        "  pending_thread_statuses = statuses or {{}}\n"
        "end\n"
        "\n"
        "local function set_pending_new_threads(threads)\n"
        "  pending_new_threads = threads or {{}}\n"
        "end\n"
        "\n"
        "local function find_section_boundaries()\n"
        "  local title_lnum = nil\n"
        "  local reviewers_lnum = nil\n"
        "  local threads_lnum = nil\n"
        "  local changes_lnum = nil\n"
        "  local policies_lnum = nil\n"
        "  local header_end = nil\n"
        "  for i = 1, vim.fn.line('$') do\n"
        "    local line = vim.fn.getline(i)\n"
        "    if line:match('^# ') and not line:match('^# Reviewers') and not line:match('^# Threads') and not line:match('^# Changes') and not line:match('^# Policies') then\n"
        "      title_lnum = i\n"
        "    elseif line:match('^# Reviewers') then\n"
        "      reviewers_lnum = i\n"
        "    elseif line:match('^# Threads') then\n"
        "      threads_lnum = i\n"
        "    elseif line:match('^# Changes') then\n"
        "      changes_lnum = i\n"
        "    elseif line:match('^# Policies') then\n"
        "      policies_lnum = i\n"
        "      break\n"
        "    end\n"
        "    if line == '' and header_end == nil and title_lnum == nil then\n"
        "      header_end = i\n"
        "    end\n"
        "  end\n"
        "  return title_lnum, reviewers_lnum, header_end, threads_lnum, changes_lnum, policies_lnum\n"
        "end\n"
        "\n"
        "local function json_value(value)\n"
        "  if value == vim.NIL then\n"
        "    return nil\n"
        "  end\n"
        "  return value\n"
        "end\n"
        "\n"
        "local function json_table(value)\n"
        "  value = json_value(value)\n"
        "  if type(value) == 'table' then\n"
        "    return value\n"
        "  end\n"
        "  return {{}}\n"
        "end\n"
        "\n"
        "local function is_system_comment(comment)\n"
        "  return json_value(comment.commentType) == 'system'\n"
        "end\n"
        "\n"
        "local function is_only_marker_content(content)\n"
        "  content = json_value(content) or ''\n"
        "  local has_visible = false\n"
        "  for raw_line in tostring(content):gmatch('[^\\n]+') do\n"
        "    local line = vim.trim(raw_line)\n"
        "    if line ~= '' and not line:match('^%[comment%]:') then\n"
        "      has_visible = true\n"
        "      break\n"
        "    end\n"
        "  end\n"
        "  return not has_visible\n"
        "end\n"
        "\n"
        "local function is_system_only_thread(thread)\n"
        "  local comments = json_table(thread.comments)\n"
        "  if #comments == 0 then\n"
        "    return false\n"
        "  end\n"
        "  for _, comment in ipairs(comments) do\n"
        "    if not is_system_comment(comment) then\n"
        "      return false\n"
        "    end\n"
        "  end\n"
        "  return true\n"
        "end\n"
        "\n"
        "local function first_display_comment(thread)\n"
        "  local comments = json_table(thread.comments)\n"
        "  local system_only = is_system_only_thread(thread)\n"
        "  for _, comment in ipairs(comments) do\n"
        "    if (system_only or not is_system_comment(comment)) and not is_only_marker_content(comment.content) then\n"
        "      return comment\n"
        "    end\n"
        "  end\n"
        "  return nil\n"
        "end\n"
        "\n"
        "local function sanitize_thread_preview(content)\n"
        "  content = tostring(json_value(content) or ''):gsub('<[^>]+>', ' ')\n"
        "  local parts = {{}}\n"
        "  for raw_line in content:gmatch('[^\\n]+') do\n"
        "    local line = vim.trim(raw_line)\n"
        "    if line ~= '' and not line:match('^%[comment%]:') then\n"
        "      table.insert(parts, line)\n"
        "    end\n"
        "  end\n"
        "  local preview = table.concat(parts, ' ')\n"
        "  preview = preview:gsub('&amp;', '&'):gsub('&lt;', '<'):gsub('&gt;', '>'):gsub('&quot;', '\"')\n"
        "  preview = preview:gsub('%s+', ' ')\n"
        "  preview = vim.trim(preview)\n"
        "  if #preview > 100 then\n"
        "    return preview:sub(1, 99) .. '...'\n"
        "  end\n"
        "  return preview\n"
        "end\n"
        "\n"
        "local function format_thread_location(thread)\n"
        "  local ctx = json_table(thread.threadContext)\n"
        "  local file_path = json_value(ctx.filePath) or ''\n"
        "  if file_path == '' then return '' end\n"
        "  local start = json_table(ctx.rightFileStart)\n"
        "  local line = json_value(start.line)\n"
        "  if line then\n"
        "    return tostring(file_path) .. ':' .. tostring(line)\n"
        "  end\n"
        "  return tostring(file_path)\n"
        "end\n"
        "\n"
        "local function format_thread_date(value)\n"
        "  value = json_value(value)\n"
        "  if not value then return '' end\n"
        "  return tostring(value):gsub('T', ' '):gsub('Z', ''):sub(1, 16)\n"
        "end\n"
        "\n"
        "local function normalize_threads_data(data)\n"
        "  if data.threads then\n"
        "    return data\n"
        "  end\n"
        "  local raw_threads = data.value or data or {{}}\n"
        "  local threads = {{}}\n"
        "  for _, thread in ipairs(raw_threads) do\n"
        "    if not (is_system_only_thread(thread) and json_value(thread.status) ~= 'active') then\n"
        "      local first = first_display_comment(thread)\n"
        "      if first then\n"
        "        local author = json_value(json_table(first.author).uniqueName) or ''\n"
        "        if author == '' and is_system_comment(first) then\n"
        "          author = 'system'\n"
        "        end\n"
        "        local ctx = json_table(thread.threadContext)\n"
        "        table.insert(threads, {{\n"
        "          id = json_value(thread.id) or '',\n"
        "          status = json_value(thread.status) or '',\n"
        "          author = author,\n"
        "          date = format_thread_date(first.publishedDate),\n"
        "          file_path = json_value(ctx.filePath) or '',\n"
        "          location = format_thread_location(thread),\n"
        "          preview = sanitize_thread_preview(first.content),\n"
        "        }})\n"
        "      end\n"
        "    end\n"
        "  end\n"
        "  return {{ threads = threads, total_threads = #threads }}\n"
        "end\n"
        "\n"
        "local function set_threads_content(data, tlnum, clnum, buf)\n"
        "  buf = buf or vim.api.nvim_get_current_buf()\n"
        "  data = normalize_threads_data(data)\n"
        "  local lines = {{ '# Threads', '' }}\n"
        "  for _, thread in ipairs(data.threads or {{}}) do\n"
        "    local display_status = pending_thread_statuses[tostring(thread.id)] or thread.status\n"
        "    local suffix = ''\n"
        "    if thread.author and thread.author ~= '' then\n"
        "      suffix = suffix .. ' by ' .. thread.author\n"
        "    end\n"
        "    if thread.location and thread.location ~= '' then\n"
        "      suffix = suffix .. ' ' .. thread.location\n"
        "    end\n"
        "    if thread.date and thread.date ~= '' then\n"
        "      suffix = suffix .. ' ' .. thread.date\n"
        "    end\n"
        "    table.insert(lines, '- [' .. thread.id .. '] (**' .. display_status .. '**)' .. suffix)\n"
        "    if thread.preview and thread.preview ~= '' then\n"
        "      table.insert(lines, '  ' .. thread.preview)\n"
        "    end\n"
        "  end\n"
        "  for _, thread in ipairs(pending_new_threads or {{}}) do\n"
        "    local line = '- [' .. thread.id .. '] (**draft**)'\n"
        "    if thread.location and thread.location ~= '' then\n"
        "      line = line .. ' ' .. thread.location\n"
        "    end\n"
        "    line = line .. ' [new]'\n"
        "    table.insert(lines, line)\n"
        "  end\n"
        "  table.insert(lines, '')\n"
        "  vim.bo[buf].modifiable = true\n"
        "  vim.api.nvim_buf_set_lines(buf, tlnum - 1, clnum - 1, false, lines)\n"
        "  vim.bo[buf].modifiable = false\n"
        "  for di = 0, #lines - 1 do\n"
        "    local thread_id = lines[di + 1]:match('^%- %[(.-)%]')\n"
        "    local pending_reply = thread_id and pending_thread_ids[tostring(thread_id)]\n"
        "    local pending_status = thread_id and pending_thread_statuses[tostring(thread_id)]\n"
        "    if pending_reply or pending_status then\n"
        "      local markers = {{}}\n"
        "      if pending_reply then\n"
        "        table.insert(markers, 'modified')\n"
        "      end\n"
        "      if pending_status then\n"
        "        table.insert(markers, pending_status)\n"
        "      end\n"
        "      pcall(vim.api.nvim_buf_set_extmark, buf, ns, tlnum - 1 + di, #lines[di + 1], {{\n"
        "        virt_text = {{{{ ' [' .. table.concat(markers, ' ') .. ']', 'WarningMsg' }}}},\n"
        "        virt_text_pos = 'eol',\n"
        "      }})\n"
        "    end\n"
        "    for _, pending in ipairs(pending_new_threads or {{}}) do\n"
        "      if thread_id and thread_id == tostring(pending.id) and pending.has_comment then\n"
        "        pcall(vim.api.nvim_buf_set_extmark, buf, ns, tlnum - 1 + di, #lines[di + 1], {{\n"
        "          virt_text = {{{{ ' [modified]', 'WarningMsg' }}}},\n"
        "          virt_text_pos = 'eol',\n"
        "        }})\n"
        "      end\n"
        "    end\n"
        "  end\n"
        "  apply_manage_modified(buf)\n"
        "end\n"
        "\n"
        "local function normalize_thread_file_path(path)\n"
        "  if not path or path == '' then\n"
        "    return ''\n"
        "  end\n"
        "  path = tostring(path)\n"
        "  path = path:gsub(':%d+$', '')\n"
        "  return path:gsub('^/+', '')\n"
        "end\n"
        "\n"
        "local function get_thread_counts_by_file()\n"
        "  local threads_path = cache_dir .. '/threads.json'\n"
        "  if vim.fn.filereadable(threads_path) ~= 1 then\n"
        "    return {{}}\n"
        "  end\n"
        "  local ok, data = pcall(vim.fn.json_decode, table.concat(vim.fn.readfile(threads_path), '\\n'))\n"
        "  if not ok then\n"
        "    return {{}}\n"
        "  end\n"
        "  data = normalize_threads_data(data)\n"
        "  local result = {{}}\n"
        "  for _, thread in ipairs(data.threads or {{}}) do\n"
        "    local filename = normalize_thread_file_path(thread.file_path or thread.location or '')\n"
        "    if filename ~= '' then\n"
        "      result[filename] = result[filename] or {{ active = 0, total = 0 }}\n"
        "      result[filename].total = result[filename].total + 1\n"
        "      if thread.status == 'active' then\n"
        "        result[filename].active = result[filename].active + 1\n"
        "      end\n"
        "    end\n"
        "  end\n"
        "  return result\n"
        "end\n"
        "\n"
        "local function set_changes_content(data, clnum, plnum, buf)\n"
        "  buf = buf or vim.api.nvim_get_current_buf()\n"
        "  local lines = {{ '# Changes', '' }}\n"
        "  local thread_counts = get_thread_counts_by_file()\n"
        "  for _, file in ipairs(data.files or {{}}) do\n"
        "    local line = file.status .. '  ' .. file.filename\n"
        "    local counts = {{}}\n"
        "    if file.added > 0 then\n"
        "      table.insert(counts, '+' .. file.added)\n"
        "    end\n"
        "    if file.deleted > 0 then\n"
        "      table.insert(counts, '-' .. file.deleted)\n"
        "    end\n"
        "    if #counts > 0 then\n"
        "      line = line .. '  ' .. table.concat(counts, ' ')\n"
        "    end\n"
        "    local file_thread_counts = thread_counts[file.filename]\n"
        "    if file_thread_counts and file_thread_counts.total > 0 then\n"
        "      line = line .. ' [' .. file_thread_counts.active .. '/' .. file_thread_counts.total .. ' threads]'\n"
        "    end\n"
        "    table.insert(lines, line)\n"
        "  end\n"
        "  if data.total_files > 0 then\n"
        "    table.insert(lines, '')\n"
        "    table.insert(lines, data.total_files .. ' files changed +' .. data.total_added .. ' -' .. data.total_deleted)\n"
        "  end\n"
        "  table.insert(lines, '')\n"
        "  vim.bo[buf].modifiable = true\n"
        "  vim.api.nvim_buf_set_lines(buf, clnum - 1, plnum - 1, false, lines)\n"
        "  vim.bo[buf].modifiable = false\n"
        "  apply_manage_modified(buf)\n"
        "\n"
        "  for di = 0, #lines - 1 do\n"
        "    local ltext = lines[di + 1]\n"
        "    local marker = ltext:sub(1, 1)\n"
        "    local marker_hl = nil\n"
        "    if marker == 'M' then\n"
        "      marker_hl = 'ChangesModifiedHL'\n"
        "    elseif marker == 'A' then\n"
        "      marker_hl = 'ChangesAddedHL'\n"
        "    elseif marker == 'D' then\n"
        "      marker_hl = 'ChangesDeletedHL'\n"
        "    end\n"
        "    if marker_hl then\n"
        "      pcall(vim.api.nvim_buf_set_extmark, buf, ns, clnum - 1 + di, 0, {{\n"
        "        end_col = 1,\n"
        "        hl_group = marker_hl,\n"
        "      }})\n"
        "    end\n"
        "    local offset = 1\n"
        "    while true do\n"
        "      local s, e = ltext:find(' %+%d+', offset)\n"
        "      if not s then break end\n"
        "      pcall(vim.api.nvim_buf_set_extmark, buf, ns, clnum - 1 + di, s, {{\n"
        "        end_col = e,\n"
        "        hl_group = 'ChangesAddHL',\n"
        "      }})\n"
        "      offset = e\n"
        "    end\n"
        "    offset = 1\n"
        "    while true do\n"
        "      local s, e = ltext:find(' %-%d+', offset)\n"
        "      if not s then break end\n"
        "      pcall(vim.api.nvim_buf_set_extmark, buf, ns, clnum - 1 + di, s, {{\n"
        "        end_col = e,\n"
        "        hl_group = 'ChangesDelHL',\n"
        "      }})\n"
        "      offset = e\n"
        "    end\n"
        "  end\n"
        "end\n"
        "\n"
        "local function policy_name(policy)\n"
        "  local cfg = json_table(policy.configuration)\n"
        "  local settings = json_table(cfg.settings)\n"
        "  local typ = json_table(cfg.type)\n"
        "  return json_value(settings.displayName) or json_value(settings.defaultDisplayName) or json_value(settings.statusName) or json_value(cfg.displayName) or json_value(typ.displayName) or ''\n"
        "end\n"
        "\n"
        "local function policy_errors(policy)\n"
        "  local ctx = json_table(policy.context)\n"
        "  local preview = json_table(ctx.buildOutputPreview)\n"
        "  local errors = json_value(preview.errors)\n"
        "  if type(errors) ~= 'table' then\n"
        "    return {{}}\n"
        "  end\n"
        "  local result = {{}}\n"
        "  for _, err in ipairs(errors) do\n"
        "    if type(err) == 'table' and json_value(err.message) and json_value(err.message) ~= '' then\n"
        "      table.insert(result, err.message)\n"
        "    elseif type(err) ~= 'table' and json_value(err) then\n"
        "      table.insert(result, tostring(err))\n"
        "    end\n"
        "  end\n"
        "  return result\n"
        "end\n"
        "\n"
        "local function policy_is_expired(policy)\n"
        "  local ctx = json_table(policy.context)\n"
        "  return json_value(policy.isExpired) or json_value(ctx.isExpired) or false\n"
        "end\n"
        "\n"
        "local function normalize_policies_data(data)\n"
        "  if data.policies then\n"
        "    return data\n"
        "  end\n"
        "  local policies = {{}}\n"
        "  for _, policy in ipairs(data or {{}}) do\n"
        "    local cfg = json_table(policy.configuration)\n"
        "    if json_value(cfg.isBlocking) then\n"
        "      table.insert(policies, {{\n"
        "        id = json_value(cfg.id) or '',\n"
        "        name = policy_name(policy),\n"
        "        status = policy_is_expired(policy) and 'expired' or json_value(policy.status) or '',\n"
        "        errors = policy_errors(policy),\n"
        "      }})\n"
        "    end\n"
        "  end\n"
        "  return {{ policies = policies, total_policies = #policies }}\n"
        "end\n"
        "\n"
        "local function set_policies_content(data, plnum, buf)\n"
        "  buf = buf or vim.api.nvim_get_current_buf()\n"
        "  data = normalize_policies_data(data)\n"
        "  local lines = {{ '# Policies', '' }}\n"
        "  for _, policy in ipairs(data.policies or {{}}) do\n"
        "    table.insert(lines, '- [' .. policy.id .. '] ' .. policy.name .. ' - **' .. policy.status .. '**')\n"
        "    for _, err in ipairs(policy.errors or {{}}) do\n"
        "      local err_text = tostring(err):gsub('\\r\\n', '\\n'):gsub('\\r', '\\n')\n"
        "      for _, err_line in ipairs(vim.split(err_text, '\\n', {{ plain = true }})) do\n"
        "        table.insert(lines, '  ' .. err_line)\n"
        "      end\n"
        "    end\n"
        "  end\n"
        "  table.insert(lines, '')\n"
        "  vim.bo[buf].modifiable = true\n"
        "  vim.api.nvim_buf_set_lines(buf, plnum - 1, -1, false, lines)\n"
        "  vim.bo[buf].modifiable = false\n"
        "  apply_manage_modified(buf)\n"
        "end\n"
        "\n"
        "local load_policies\n"
        "\n"
        "local function current_policy_id()\n"
        "  local _, _, _, _, _, policies_lnum = find_section_boundaries()\n"
        "  if not policies_lnum or vim.fn.line('.') <= policies_lnum then\n"
        "    return nil\n"
        "  end\n"
        "  local policy_id = vim.fn.getline('.'):match('^%- %[(.-)%]')\n"
        "  return policy_id\n"
        "end\n"
        "\n"
        "local function queue_current_policy()\n"
        "  local policy_id = current_policy_id()\n"
        "  if not policy_id or policy_id == '' then\n"
        "    vim.notify('Place cursor on a policy line to queue it', vim.log.levels.WARN)\n"
        "    return\n"
        "  end\n"
        "  vim.notify('Queueing policy...', vim.log.levels.INFO)\n"
        "  local job_output = {{}}\n"
        "  local job_id = vim.fn.jobstart({{'gg', 'pr', '_manage-policy-queue', tostring(pr_id), tostring(policy_id)}}, {{\n"
        "    stdout_buffered = true,\n"
        "    on_stdout = function(_, data, _)\n"
        "      if data then\n"
        "        for _, line in ipairs(data) do\n"
        "          table.insert(job_output, line)\n"
        "        end\n"
        "      end\n"
        "    end,\n"
        "    on_exit = function(_, exit_code, _)\n"
        "      vim.schedule(function()\n"
        "        local result = table.concat(job_output, '\\n')\n"
        "        local ok, data = pcall(vim.fn.json_decode, result)\n"
        "        if exit_code == 0 and ok and data.status == 'ok' then\n"
        "          vim.notify('Policy queued', vim.log.levels.INFO)\n"
        "          load_policies(true)\n"
        "        else\n"
        "          local message = ok and data.message or result\n"
        "          if message == '' then message = 'exit ' .. exit_code end\n"
        "          vim.notify('Policy queue failed: ' .. tostring(message), vim.log.levels.ERROR)\n"
        "        end\n"
        "      end)\n"
        "    end,\n"
        "  }})\n"
        "  if job_id <= 0 then\n"
        "    vim.notify('Policy queue failed to start', vim.log.levels.ERROR)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function cancel_current_policy()\n"
        "  local policy_id = current_policy_id()\n"
        "  if not policy_id or policy_id == '' then\n"
        "    vim.notify('Place cursor on a policy line to cancel it', vim.log.levels.WARN)\n"
        "    return\n"
        "  end\n"
        "  vim.notify('Canceling policy...', vim.log.levels.INFO)\n"
        "  local job_output = {{}}\n"
        "  local job_id = vim.fn.jobstart({{'gg', 'pr', '_manage-policy-cancel', tostring(pr_id), tostring(policy_id)}}, {{\n"
        "    stdout_buffered = true,\n"
        "    on_stdout = function(_, data, _)\n"
        "      if data then\n"
        "        for _, line in ipairs(data) do\n"
        "          table.insert(job_output, line)\n"
        "        end\n"
        "      end\n"
        "    end,\n"
        "    on_exit = function(_, exit_code, _)\n"
        "      vim.schedule(function()\n"
        "        local result = table.concat(job_output, '\\n')\n"
        "        local ok, data = pcall(vim.fn.json_decode, result)\n"
        "        if exit_code == 0 and ok and data.status == 'ok' then\n"
        "          vim.notify('Policy canceled', vim.log.levels.INFO)\n"
        "          load_policies(true)\n"
        "        else\n"
        "          local message = ok and data.message or result\n"
        "          if message == '' then message = 'exit ' .. exit_code end\n"
        "          vim.notify('Policy cancel failed: ' .. tostring(message), vim.log.levels.ERROR)\n"
        "        end\n"
        "      end)\n"
        "    end,\n"
        "  }})\n"
        "  if job_id <= 0 then\n"
        "    vim.notify('Policy cancel failed to start', vim.log.levels.ERROR)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function refresh_changes_from_cache(buf)\n"
        "  local changes_path = cache_dir .. '/changes.json'\n"
        "  if vim.fn.filereadable(changes_path) ~= 1 then\n"
        "    return\n"
        "  end\n"
        "  local ok, data = pcall(vim.fn.json_decode, table.concat(vim.fn.readfile(changes_path), '\\n'))\n"
        "  if ok and data.files then\n"
        "    local _, _, _, _, changes_lnum, policies_lnum = find_section_boundaries()\n"
        "    if changes_lnum and policies_lnum then\n"
        "      set_changes_content(data, changes_lnum, policies_lnum, buf)\n"
        "    end\n"
        "  end\n"
        "end\n"
        "\n"
        "local changes_loading = false\n"
        "local threads_loading = false\n"
        "local policies_loading = false\n"
        "local changes_loading_mark = nil\n"
        "local threads_loading_mark = nil\n"
        "local policies_loading_mark = nil\n"
        "local changes_job_id = nil\n"
        "local threads_job_id = nil\n"
        "local policies_job_id = nil\n"
        "local diff_open_job_id = nil\n"
        "\n"
        "local function load_threads(force)\n"
        "  local threads_path = cache_dir .. '/threads.json'\n"
        "  local buf = vim.api.nvim_get_current_buf()\n"
        "\n"
        "  if force and threads_job_id then\n"
        "    pcall(vim.fn.jobstop, threads_job_id)\n"
        "    threads_job_id = nil\n"
        "    threads_loading = false\n"
        "    if threads_loading_mark then\n"
        "      pcall(vim.api.nvim_buf_del_extmark, buf, ns, threads_loading_mark)\n"
        "      threads_loading_mark = nil\n"
        "    end\n"
        "  end\n"
        "\n"
        "  if force then\n"
        "    pcall(vim.fn.delete, threads_path)\n"
        "  end\n"
        "\n"
        "  if not force and vim.fn.filereadable(threads_path) == 1 then\n"
        "    local ok, data = pcall(vim.fn.json_decode, table.concat(vim.fn.readfile(threads_path), '\\n'))\n"
        "    if ok then\n"
        "      local _, _, _, threads_lnum, changes_lnum = find_section_boundaries()\n"
        "      if threads_lnum and changes_lnum then\n"
        "        set_threads_content(data, threads_lnum, changes_lnum, buf)\n"
        "        refresh_changes_from_cache(buf)\n"
        "      end\n"
        "      return\n"
        "    end\n"
        "  end\n"
        "\n"
        "  if threads_loading then return end\n"
        "\n"
        "  local _, _, _, threads_lnum, changes_lnum = find_section_boundaries()\n"
        "  if not threads_lnum or not changes_lnum then return end\n"
        "\n"
        "  threads_loading_mark = vim.api.nvim_buf_set_extmark(buf, ns, threads_lnum - 1, 0, {{\n"
        "    virt_text = {{{{ ' [loading]', 'WarningMsg' }}}},\n"
        "    virt_text_pos = 'eol',\n"
        "  }})\n"
        "\n"
        "  threads_loading = true\n"
        "  local job_output = {{}}\n"
        "  local job_id = vim.fn.jobstart({{'gg', 'pr', '_manage-threads', tostring(pr_id)}}, {{\n"
        "    stdout_buffered = true,\n"
        "    on_stdout = function(_, data, _)\n"
        "      if data then\n"
        "        for _, line in ipairs(data) do\n"
        "          table.insert(job_output, line)\n"
        "        end\n"
        "      end\n"
        "    end,\n"
        "    on_exit = function(job_id_done, exit_code, _)\n"
        "      vim.schedule(function()\n"
        "        if threads_job_id ~= job_id_done then\n"
        "          return\n"
        "        end\n"
        "        threads_job_id = nil\n"
        "        threads_loading = false\n"
        "        if threads_loading_mark then\n"
        "          pcall(vim.api.nvim_buf_del_extmark, buf, ns, threads_loading_mark)\n"
        "          threads_loading_mark = nil\n"
        "        end\n"
        "        if exit_code ~= 0 then\n"
        "          vim.notify('Threads load failed (exit ' .. exit_code .. ')', vim.log.levels.WARN)\n"
        "          return\n"
        "        end\n"
        "        local result = table.concat(job_output, '\\n')\n"
        "        local ok, data2 = pcall(vim.fn.json_decode, result)\n"
        "        if ok and data2.status == 'ok' then\n"
        "          local _, _, _, tlnum, clnum = find_section_boundaries()\n"
        "          if tlnum and clnum then\n"
        "            set_threads_content(data2, tlnum, clnum, buf)\n"
        "            refresh_changes_from_cache(buf)\n"
        "          end\n"
        "        end\n"
        "      end)\n"
        "    end,\n"
        "  }})\n"
        "  threads_job_id = job_id\n"
        "  if job_id <= 0 then\n"
        "    threads_job_id = nil\n"
        "    threads_loading = false\n"
        "    if threads_loading_mark then\n"
        "      pcall(vim.api.nvim_buf_del_extmark, buf, ns, threads_loading_mark)\n"
        "      threads_loading_mark = nil\n"
        "    end\n"
        "    vim.notify('Threads load failed to start', vim.log.levels.WARN)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function load_changes(force)\n"
        "  local changes_path = cache_dir .. '/changes.json'\n"
        "\n"
        "  local buf = vim.api.nvim_get_current_buf()\n"
        "\n"
        "  if force and changes_job_id then\n"
        "    pcall(vim.fn.jobstop, changes_job_id)\n"
        "    changes_job_id = nil\n"
        "    changes_loading = false\n"
        "    if changes_loading_mark then\n"
        "      pcall(vim.api.nvim_buf_del_extmark, buf, ns, changes_loading_mark)\n"
        "      changes_loading_mark = nil\n"
        "    end\n"
        "  end\n"
        "\n"
        "  if force then\n"
        "    pcall(vim.fn.delete, changes_path)\n"
        "  end\n"
        "\n"
        "  if not force and vim.fn.filereadable(changes_path) == 1 then\n"
        "    local ok, data = pcall(vim.fn.json_decode, table.concat(vim.fn.readfile(changes_path), '\\n'))\n"
        "    if ok and data.files then\n"
        "      local _, _, _, _, changes_lnum, policies_lnum = find_section_boundaries()\n"
        "      if changes_lnum and policies_lnum then\n"
        "        set_changes_content(data, changes_lnum, policies_lnum, buf)\n"
        "      end\n"
        "      return\n"
        "    end\n"
        "  end\n"
        "\n"
        "  if changes_loading then return end\n"
        "\n"
        "  local _, _, _, _, changes_lnum, policies_lnum = find_section_boundaries()\n"
        "  if not changes_lnum or not policies_lnum then return end\n"
        "\n"
        "  changes_loading_mark = vim.api.nvim_buf_set_extmark(buf, ns, changes_lnum - 1, 0, {{\n"
        "    virt_text = {{{{ ' [loading]', 'WarningMsg' }}}},\n"
        "    virt_text_pos = 'eol',\n"
        "  }})\n"
        "\n"
        "  changes_loading = true\n"
        "  local job_output = {{}}\n"
        "  local job_id = vim.fn.jobstart({{'gg', 'pr', '_manage-changes', tostring(pr_id)}}, {{\n"
        "    stdout_buffered = true,\n"
        "    on_stdout = function(_, data, _)\n"
        "      if data then\n"
        "        for _, line in ipairs(data) do\n"
        "          table.insert(job_output, line)\n"
        "        end\n"
        "      end\n"
        "    end,\n"
        "    on_exit = function(job_id_done, exit_code, _)\n"
        "      vim.schedule(function()\n"
        "        if changes_job_id ~= job_id_done then\n"
        "          return\n"
        "        end\n"
        "        changes_job_id = nil\n"
        "        changes_loading = false\n"
        "        if changes_loading_mark then\n"
        "          pcall(vim.api.nvim_buf_del_extmark, buf, ns, changes_loading_mark)\n"
        "          changes_loading_mark = nil\n"
        "        end\n"
        "        if exit_code ~= 0 then\n"
        "          vim.notify('Changes load failed (exit ' .. exit_code .. ')', vim.log.levels.WARN)\n"
        "          return\n"
        "        end\n"
        "        local result = table.concat(job_output, '\\n')\n"
        "        local ok, data2 = pcall(vim.fn.json_decode, result)\n"
        "        if ok and data2.status == 'ok' then\n"
        "          local _, _, _, _, clnum, plnum = find_section_boundaries()\n"
        "          if clnum and plnum then\n"
        "            set_changes_content(data2, clnum, plnum, buf)\n"
        "          end\n"
        "        end\n"
        "      end)\n"
        "    end,\n"
        "  }})\n"
        "  changes_job_id = job_id\n"
        "  if job_id <= 0 then\n"
        "    changes_job_id = nil\n"
        "    changes_loading = false\n"
        "    if changes_loading_mark then\n"
        "      pcall(vim.api.nvim_buf_del_extmark, buf, ns, changes_loading_mark)\n"
        "      changes_loading_mark = nil\n"
        "    end\n"
        "    vim.notify('Changes load failed to start', vim.log.levels.WARN)\n"
        "  end\n"
        "end\n"
        "\n"
        "load_policies = function(force)\n"
        "  local policies_path = cache_dir .. '/policies.json'\n"
        "  local buf = vim.api.nvim_get_current_buf()\n"
        "\n"
        "  if force and policies_job_id then\n"
        "    pcall(vim.fn.jobstop, policies_job_id)\n"
        "    policies_job_id = nil\n"
        "    policies_loading = false\n"
        "    if policies_loading_mark then\n"
        "      pcall(vim.api.nvim_buf_del_extmark, buf, ns, policies_loading_mark)\n"
        "      policies_loading_mark = nil\n"
        "    end\n"
        "  end\n"
        "\n"
        "  if force then\n"
        "    pcall(vim.fn.delete, policies_path)\n"
        "  end\n"
        "\n"
        "  if not force and vim.fn.filereadable(policies_path) == 1 then\n"
        "    local ok, data = pcall(vim.fn.json_decode, table.concat(vim.fn.readfile(policies_path), '\\n'))\n"
        "    if ok then\n"
        "      local _, _, _, _, _, policies_lnum = find_section_boundaries()\n"
        "      if policies_lnum then\n"
        "        set_policies_content(data, policies_lnum, buf)\n"
        "      end\n"
        "      return\n"
        "    end\n"
        "  end\n"
        "\n"
        "  if policies_loading then return end\n"
        "\n"
        "  local _, _, _, _, _, policies_lnum = find_section_boundaries()\n"
        "  if not policies_lnum then return end\n"
        "\n"
        "  policies_loading_mark = vim.api.nvim_buf_set_extmark(buf, ns, policies_lnum - 1, 0, {{\n"
        "    virt_text = {{{{ ' [loading]', 'WarningMsg' }}}},\n"
        "    virt_text_pos = 'eol',\n"
        "  }})\n"
        "\n"
        "  policies_loading = true\n"
        "  local job_output = {{}}\n"
        "  local job_id = vim.fn.jobstart({{'gg', 'pr', '_manage-policies', tostring(pr_id)}}, {{\n"
        "    stdout_buffered = true,\n"
        "    on_stdout = function(_, data, _)\n"
        "      if data then\n"
        "        for _, line in ipairs(data) do\n"
        "          table.insert(job_output, line)\n"
        "        end\n"
        "      end\n"
        "    end,\n"
        "    on_exit = function(job_id_done, exit_code, _)\n"
        "      vim.schedule(function()\n"
        "        if policies_job_id ~= job_id_done then\n"
        "          return\n"
        "        end\n"
        "        policies_job_id = nil\n"
        "        policies_loading = false\n"
        "        if policies_loading_mark then\n"
        "          pcall(vim.api.nvim_buf_del_extmark, buf, ns, policies_loading_mark)\n"
        "          policies_loading_mark = nil\n"
        "        end\n"
        "        if exit_code ~= 0 then\n"
        "          vim.notify('Policies load failed (exit ' .. exit_code .. ')', vim.log.levels.WARN)\n"
        "          return\n"
        "        end\n"
        "        local result = table.concat(job_output, '\\n')\n"
        "        local ok, data2 = pcall(vim.fn.json_decode, result)\n"
        "        if ok and data2.status == 'ok' then\n"
        "          local _, _, _, _, _, plnum = find_section_boundaries()\n"
        "          if plnum then\n"
        "            set_policies_content(data2, plnum, buf)\n"
        "          end\n"
        "        end\n"
        "      end)\n"
        "    end,\n"
        "  }})\n"
        "  policies_job_id = job_id\n"
        "  if job_id <= 0 then\n"
        "    policies_job_id = nil\n"
        "    policies_loading = false\n"
        "    if policies_loading_mark then\n"
        "      pcall(vim.api.nvim_buf_del_extmark, buf, ns, policies_loading_mark)\n"
        "      policies_loading_mark = nil\n"
        "    end\n"
        "    vim.notify('Policies load failed to start', vim.log.levels.WARN)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function sync_view(load_sections)\n"
        "  if load_sections == nil then\n"
        "    load_sections = true\n"
        "  end\n"
        "  local result = vim.fn.system({{'gg', 'pr', '_manage', tostring(pr_id)}})\n"
        "  local ok, data = pcall(vim.fn.json_decode, result)\n"
        "  if not ok or data.status ~= 'ok' then\n"
        "    return\n"
        "  end\n"
        "  vim.api.nvim_buf_clear_namespace(0, ns, 0, -1)\n"
        "  set_pending_thread_ids(data.pending_thread_ids)\n"
        "  set_pending_thread_status_ids(data.pending_thread_status_ids)\n"
        "  set_pending_thread_statuses(data.pending_thread_statuses)\n"
        "  set_pending_new_threads(data.pending_new_threads)\n"
        "  manage_has_pending_changes = data.changed or data.status_changed or data.vote_changed or data.thread_responses_changed or data.thread_statuses_changed or data.new_threads_changed\n"
        "\n"
        "  local title_lnum, reviewers_lnum, _, threads_lnum = find_section_boundaries()\n"
        "\n"
        "  if title_lnum and reviewers_lnum then\n"
        "    local new_lines = {{}}\n"
        "    table.insert(new_lines, '# ' .. data.title)\n"
        "    table.insert(new_lines, '')\n"
        "    for _, ln in ipairs(data.description_lines or {{}}) do\n"
        "      table.insert(new_lines, ln)\n"
        "    end\n"
        "    if new_lines[#new_lines] ~= '' then\n"
        "      table.insert(new_lines, '')\n"
        "    end\n"
        "    vim.bo.modifiable = true\n"
        "    vim.api.nvim_buf_set_lines(0, title_lnum - 1, reviewers_lnum - 1, false, new_lines)\n"
        "    vim.bo.modifiable = false\n"
        "  end\n"
        "\n"
        "  title_lnum, reviewers_lnum, _, threads_lnum = find_section_boundaries()\n"
        "\n"
        "  if reviewers_lnum and threads_lnum then\n"
        "    vim.bo.modifiable = true\n"
        "    vim.api.nvim_buf_set_lines(0, reviewers_lnum - 1, threads_lnum - 1, false, data.reviewer_lines or {{ '# Reviewers', '' }})\n"
        "    vim.bo.modifiable = false\n"
        "  end\n"
        "\n"
        "  for i = 1, vim.fn.line('$') do\n"
        "    local line = vim.fn.getline(i)\n"
        "    if line:match('^status:') then\n"
        "      vim.bo.modifiable = true\n"
        "      if data.status_changed then\n"
        "        local status_text = 'status: ' .. data.original_status .. ' -> ' .. data.pr_status\n"
        "        vim.api.nvim_buf_set_lines(0, i - 1, i, false, {{status_text}})\n"
        "        vim.api.nvim_buf_set_extmark(0, ns, i - 1, #status_text, {{\n"
        "          virt_text = {{{{ ' [modified]', 'WarningMsg' }}}},\n"
        "          virt_text_pos = 'eol',\n"
        "        }})\n"
        "      else\n"
        "        vim.api.nvim_buf_set_lines(0, i - 1, i, false, {{'status: ' .. data.pr_status}})\n"
        "      end\n"
        "      vim.bo.modifiable = false\n"
        "      break\n"
        "    end\n"
        "  end\n"
        "\n"
        "  if data.changed then\n"
        "    for i = 1, vim.fn.line('$') do\n"
        "      local line = vim.fn.getline(i)\n"
        "      if line:match('^# ') and not line:match('^# Reviewers') and not line:match('^# Threads') and not line:match('^# Changes') and not line:match('^# Policies') then\n"
        "        vim.api.nvim_buf_set_extmark(0, ns, i - 1, 0, {{\n"
        "          virt_text = {{{{' [modified]', 'WarningMsg'}}}},\n"
        "          virt_text_pos = 'eol',\n"
        "        }})\n"
        "        break\n"
        "      end\n"
        "    end\n"
        "  end\n"
        "  if data.vote_changed then\n"
        "    for i = 1, vim.fn.line('$') do\n"
        "      if vim.fn.getline(i):match('^# Reviewers') then\n"
        "        vim.api.nvim_buf_set_extmark(0, ns, i - 1, 0, {{\n"
        "          virt_text = {{{{ ' [vote: ' .. data.pending_vote_label .. ']', 'WarningMsg' }}}},\n"
        "          virt_text_pos = 'eol',\n"
        "        }})\n"
        "        break\n"
        "      end\n"
        "    end\n"
        "  end\n"
        "  if load_sections then\n"
        "    load_threads(false)\n"
        "    load_changes(false)\n"
        "    load_policies(false)\n"
        "  end\n"
        "  apply_manage_modified(0)\n"
        "end\n"
        "\n"
        "local function reload_pr_details(load_sections, on_done)\n"
        "  local job_output = {{}}\n"
        "  local job_id = vim.fn.jobstart({{'gg', 'pr', '_manage-reload', tostring(pr_id)}}, {{\n"
        "    stdout_buffered = true,\n"
        "    on_stdout = function(_, data, _)\n"
        "      if data then\n"
        "        for _, line in ipairs(data) do\n"
        "          table.insert(job_output, line)\n"
        "        end\n"
        "      end\n"
        "    end,\n"
        "    on_exit = function(_, exit_code, _)\n"
        "      vim.schedule(function()\n"
        "        local result = table.concat(job_output, '\\n')\n"
        "        local ok, data = pcall(vim.fn.json_decode, result)\n"
        "        if exit_code == 0 and ok and data.status == 'ok' then\n"
        "          sync_view(load_sections)\n"
        "          if on_done then on_done() end\n"
        "          return\n"
        "        end\n"
        "        local message = ok and data.message or result\n"
        "        if message == '' then message = 'exit ' .. exit_code end\n"
        "        vim.notify('Reload failed: ' .. tostring(message), vim.log.levels.ERROR)\n"
        "      end)\n"
        "    end,\n"
        "  }})\n"
        "  if job_id <= 0 then\n"
        "    vim.notify('Reload failed to start', vim.log.levels.ERROR)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function current_section()\n"
        "  local _, _, _, threads_lnum, changes_lnum, policies_lnum = find_section_boundaries()\n"
        "  local cursor_line = vim.fn.line('.')\n"
        "  if policies_lnum and cursor_line >= policies_lnum then\n"
        "    return 'policies'\n"
        "  end\n"
        "  if changes_lnum and cursor_line >= changes_lnum and (not policies_lnum or cursor_line < policies_lnum) then\n"
        "    return 'changes'\n"
        "  end\n"
        "  if threads_lnum and cursor_line >= threads_lnum and (not changes_lnum or cursor_line < changes_lnum) then\n"
        "    return 'threads'\n"
        "  end\n"
        "  return 'details'\n"
        "end\n"
        "\n"
        "local function current_thread_id()\n"
        "  if current_section() ~= 'threads' then\n"
        "    return nil\n"
        "  end\n"
        "  return vim.fn.getline('.'):match('^%- %[(.-)%]')\n"
        "end\n"
        "\n"
        "local function open_thread_by_id(thread_id)\n"
        "  if tostring(thread_id):match('^new%-') then\n"
        "    vim.cmd('edit ' .. vim.fn.fnameescape(cache_dir .. '/threads/' .. tostring(thread_id) .. '.md'))\n"
        "    return\n"
        "  end\n"
        "  local result = vim.fn.system({{'gg', 'pr', '_manage-thread-open', tostring(pr_id), tostring(thread_id)}})\n"
        "  local ok, data = pcall(vim.fn.json_decode, result)\n"
        "  if ok and data.status == 'ok' then\n"
        "    vim.cmd('edit ' .. vim.fn.fnameescape(data.path))\n"
        "  else\n"
        "    local message = ok and data.message or result\n"
        "    vim.notify('Thread open failed: ' .. tostring(message), vim.log.levels.ERROR)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function open_current_thread()\n"
        "  local thread_id = current_thread_id()\n"
        "  if not thread_id or thread_id == '' then\n"
        "    vim.notify('Place cursor on a thread line to open it', vim.log.levels.WARN)\n"
        "    return\n"
        "  end\n"
        "  open_thread_by_id(thread_id)\n"
        "end\n"
        "\n"
        "local function set_current_thread_status(status)\n"
        "  local thread_id = current_thread_id()\n"
        "  if not thread_id or thread_id == '' then\n"
        "    return\n"
        "  end\n"
        "  local result = vim.fn.system({{'gg', 'pr', '_manage-thread-status', tostring(pr_id), tostring(thread_id), status}})\n"
        "  local ok, data = pcall(vim.fn.json_decode, result)\n"
        "  if ok and data.status == 'ok' then\n"
        "    sync_view(false)\n"
        "    load_threads(false)\n"
        "    vim.notify('Thread status pending: ' .. status, vim.log.levels.INFO)\n"
        "  else\n"
        "    local message = ok and data.message or result\n"
        "    vim.notify('Thread status failed: ' .. tostring(message), vim.log.levels.ERROR)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function create_new_thread(location)\n"
        "  local cmd = {{'gg', 'pr', '_manage-thread-new', tostring(pr_id)}}\n"
        "  if location then\n"
        "    table.insert(cmd, '--file-path')\n"
        "    table.insert(cmd, location.file_path)\n"
        "    table.insert(cmd, '--side')\n"
        "    table.insert(cmd, location.side)\n"
        "    table.insert(cmd, '--line')\n"
        "    table.insert(cmd, tostring(location.line))\n"
        "  end\n"
        "  local result = vim.fn.system(cmd)\n"
        "  local ok, data = pcall(vim.fn.json_decode, result)\n"
        "  if ok and data.status == 'ok' then\n"
        "    vim.cmd('edit ' .. vim.fn.fnameescape(data.path))\n"
        "  else\n"
        "    local message = ok and data.message or result\n"
        "    vim.notify('New thread draft failed: ' .. tostring(message), vim.log.levels.ERROR)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function apply_diff_annotations(annotations, line_map)\n"
        "  local buf = vim.api.nvim_get_current_buf()\n"
        "  line_map = line_map or {{}}\n"
        "  vim.api.nvim_buf_clear_namespace(buf, ns, 0, -1)\n"
        "  local thread_lines = {{}}\n"
        "  local threads_by_line = {{}}\n"
        "  for _, annotation in ipairs(annotations or {{}}) do\n"
        "    local diff_line = tonumber(annotation.diff_line)\n"
        "    if diff_line and diff_line > 0 then\n"
        "      table.insert(thread_lines, diff_line)\n"
        "      threads_by_line[diff_line] = threads_by_line[diff_line] or {{}}\n"
        "      table.insert(threads_by_line[diff_line], annotation)\n"
        "      local status = annotation.status or ''\n"
        "      local preview = annotation.preview or ''\n"
        "      local text = ' [thread ' .. tostring(annotation.thread_id)\n"
        "      if status ~= '' then\n"
        "        text = text .. ' ' .. status\n"
        "      end\n"
        "      text = text .. ']'\n"
        "      if preview ~= '' then\n"
        "        text = text .. ' ' .. preview\n"
        "      end\n"
        "      local hl = status == 'active' and 'ThreadActiveHL' or 'DiffThreadHL'\n"
        "      pcall(vim.api.nvim_buf_set_extmark, buf, ns, diff_line - 1, 0, {{\n"
        "        virt_text = {{{{ text, hl }}}},\n"
        "        virt_text_pos = 'eol',\n"
        "      }})\n"
        "    end\n"
        "  end\n"
        "  table.sort(thread_lines)\n"
        "  local deduped = {{}}\n"
        "  for _, line in ipairs(thread_lines) do\n"
        "    if deduped[#deduped] ~= line then\n"
        "      table.insert(deduped, line)\n"
        "    end\n"
        "  end\n"
        "  thread_lines = deduped\n"
        "  local function jump_thread(delta)\n"
        "    if #thread_lines == 0 then\n"
        "      vim.notify('No thread locations in diff', vim.log.levels.INFO)\n"
        "      return\n"
        "    end\n"
        "    local current = vim.fn.line('.')\n"
        "    local target = nil\n"
        "    if delta > 0 then\n"
        "      for _, line in ipairs(thread_lines) do\n"
        "        if line > current then\n"
        "          target = line\n"
        "          break\n"
        "        end\n"
        "      end\n"
        "      target = target or thread_lines[1]\n"
        "    else\n"
        "      for i = #thread_lines, 1, -1 do\n"
        "        local line = thread_lines[i]\n"
        "        if line < current then\n"
        "          target = line\n"
        "          break\n"
        "        end\n"
        "      end\n"
        "      target = target or thread_lines[#thread_lines]\n"
        "    end\n"
        "    vim.api.nvim_win_set_cursor(0, {{ target, 0 }})\n"
        "  end\n"
        "  local function open_thread_at_cursor()\n"
        "    local line_threads = threads_by_line[vim.fn.line('.')]\n"
        "    if not line_threads or #line_threads == 0 then\n"
        "      return\n"
        "    end\n"
        "    if #line_threads == 1 then\n"
        "      open_thread_by_id(line_threads[1].thread_id)\n"
        "      return\n"
        "    end\n"
        "    vim.ui.select(line_threads, {{\n"
        "      prompt = 'Select thread:',\n"
        "      format_item = function(item)\n"
        "        local label = 'thread ' .. tostring(item.thread_id)\n"
        "        if item.status and item.status ~= '' then\n"
        "          label = label .. ' ' .. item.status\n"
        "        end\n"
        "        if item.preview and item.preview ~= '' then\n"
        "          label = label .. ': ' .. item.preview\n"
        "        end\n"
        "        return label\n"
        "      end,\n"
        "    }}, function(choice)\n"
        "      if choice then\n"
        "        open_thread_by_id(choice.thread_id)\n"
        "      end\n"
        "    end)\n"
        "  end\n"
        "  local function add_thread_at_cursor()\n"
        "    local location = line_map[tostring(vim.fn.line('.'))]\n"
        "    if not location then\n"
        "      return\n"
        "    end\n"
        "    create_new_thread(location)\n"
        "  end\n"
        "  vim.keymap.set('n', ']]', function() jump_thread(1) end, {{ buffer = buf, noremap = true, silent = true }})\n"
        "  vim.keymap.set('n', '[[', function() jump_thread(-1) end, {{ buffer = buf, noremap = true, silent = true }})\n"
        "  vim.keymap.set('n', 'o', open_thread_at_cursor, {{ buffer = buf, noremap = true, silent = true }})\n"
        "  vim.keymap.set('n', 'a', add_thread_at_cursor, {{ buffer = buf, noremap = true, silent = true }})\n"
        "end\n"
        "\n"
        "local function open_changes_diff()\n"
        "  if diff_open_job_id then\n"
        "    vim.notify('Diff is already opening...', vim.log.levels.INFO)\n"
        "    return\n"
        "  end\n"
        "  vim.notify('Generating diff...', vim.log.levels.INFO)\n"
        "  local job_output = {{}}\n"
        "  local job_id = vim.fn.jobstart({{'gg', 'pr', '_manage-diff-open', tostring(pr_id)}}, {{\n"
        "    stdout_buffered = true,\n"
        "    on_stdout = function(_, data, _)\n"
        "      if data then\n"
        "        for _, line in ipairs(data) do\n"
        "          table.insert(job_output, line)\n"
        "        end\n"
        "      end\n"
        "    end,\n"
        "    on_exit = function(job_id_done, exit_code, _)\n"
        "      vim.schedule(function()\n"
        "        if diff_open_job_id ~= job_id_done then\n"
        "          return\n"
        "        end\n"
        "        diff_open_job_id = nil\n"
        "        local result = table.concat(job_output, '\\n')\n"
        "        local ok, data = pcall(vim.fn.json_decode, result)\n"
        "        if exit_code == 0 and ok and data.status == 'ok' then\n"
        "          vim.cmd('edit ' .. vim.fn.fnameescape(data.path))\n"
        "          vim.bo.filetype = 'diff'\n"
        "          vim.bo.modifiable = false\n"
        "          apply_diff_annotations(data.annotations, data.line_map)\n"
        "          return\n"
        "        end\n"
        "        local message = ok and data.message or result\n"
        "        if message == '' then message = 'exit ' .. exit_code end\n"
        "        vim.notify('Diff open failed: ' .. tostring(message), vim.log.levels.ERROR)\n"
        "      end)\n"
        "    end,\n"
        "  }})\n"
        "  diff_open_job_id = job_id\n"
        "  if job_id <= 0 then\n"
        "    diff_open_job_id = nil\n"
        "    vim.notify('Diff open failed to start', vim.log.levels.ERROR)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function open_summary()\n"
        "  local result = vim.fn.system({{'gg', 'pr', '_fetch-summary', tostring(pr_id)}})\n"
        "  local ok, data = pcall(vim.fn.json_decode, result)\n"
        "  if ok and data.status == 'ok' then\n"
        "    vim.cmd('edit ' .. vim.fn.fnameescape(data.path))\n"
        "  else\n"
        "    vim.notify('_fetch-summary failed: ' .. tostring(result), vim.log.levels.ERROR)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function open_current_item()\n"
        "  local section = current_section()\n"
        "  if section == 'changes' then\n"
        "    open_changes_diff()\n"
        "  elseif section == 'threads' then\n"
        "    open_current_thread()\n"
        "  else\n"
        "    open_summary()\n"
        "  end\n"
        "end\n"
        "\n"
        "local function add_current_item()\n"
        "  local section = current_section()\n"
        "  if section == 'policies' then\n"
        "    queue_current_policy()\n"
        "  elseif section == 'threads' then\n"
        "    create_new_thread(nil)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function cancel_current_item()\n"
        "  if current_section() == 'policies' then\n"
        "    cancel_current_policy()\n"
        "  end\n"
        "end\n"
        "\n"
        "local function reload_current_section()\n"
        "  local section = current_section()\n"
        "  if section == 'changes' then\n"
        "    load_changes(true)\n"
        "    vim.notify('Reloading changes...', vim.log.levels.INFO)\n"
        "  elseif section == 'policies' then\n"
        "    load_policies(true)\n"
        "    vim.notify('Reloading policies...', vim.log.levels.INFO)\n"
        "  elseif section == 'threads' then\n"
        "    load_threads(true)\n"
        "    vim.notify('Reloading threads...', vim.log.levels.INFO)\n"
        "  else\n"
        "    reload_pr_details(true, function()\n"
        "      vim.notify('PR details reloaded', vim.log.levels.INFO)\n"
        "    end)\n"
        "  end\n"
        "end\n"
        "\n"
        "local function reload_everything()\n"
        "  reload_pr_details(false, function()\n"
        "    load_threads(true)\n"
        "    load_changes(true)\n"
        "    load_policies(true)\n"
        "    vim.notify('Reloading PR, threads, changes, and policies...', vim.log.levels.INFO)\n"
        "  end)\n"
        "end\n"
        "\n"
        "local function open_action_menu()\n"
        "  vim.ui.select(ACTIONS, {{\n"
        "    prompt = 'Select PR action:',\n"
        "    format_item = function(item) return item.label end,\n"
        "  }}, function(choice)\n"
        "    if not choice then\n"
        "      return\n"
        "    end\n"
        "    local cmd = choice.kind == 'status'\n"
        "      and {{'gg', 'pr', '_set-status', tostring(pr_id), choice.value}}\n"
        "      or {{'gg', 'pr', '_set-vote', tostring(pr_id), choice.value}}\n"
        "    local result = vim.fn.system(cmd)\n"
        "    local ok, data = pcall(vim.fn.json_decode, result)\n"
        "    if ok and data.status == 'ok' then\n"
        "      sync_view()\n"
        "      vim.notify(choice.label .. ' pending', vim.log.levels.INFO)\n"
        "    else\n"
        "      vim.notify('Failed to stage action: ' .. tostring(result), vim.log.levels.ERROR)\n"
        "    end\n"
        "  end)\n"
        "end\n"
        "\n"
        "vim.api.nvim_create_autocmd('BufEnter', {{\n"
        "  pattern = manage_path,\n"
        "  callback = function()\n"
        "    vim.bo.filetype = 'markdown'\n"
        "    vim.bo.modifiable = false\n"
        "    sync_view()\n"
        "  end,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'A', '', {{\n"
        "  callback = open_action_menu,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'cc', '', {{\n"
        "  callback = function()\n"
        "    if current_section() == 'threads' then\n"
        "      set_current_thread_status('closed')\n"
        "    end\n"
        "  end,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'ca', '', {{\n"
        "  callback = function()\n"
        "    if current_section() == 'threads' then set_current_thread_status('active') end\n"
        "  end,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'cf', '', {{\n"
        "  callback = function()\n"
        "    if current_section() == 'threads' then set_current_thread_status('fixed') end\n"
        "  end,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'cw', '', {{\n"
        "  callback = function()\n"
        "    if current_section() == 'threads' then set_current_thread_status('wontFix') end\n"
        "  end,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'r', '', {{\n"
        "  callback = reload_current_section,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'R', '', {{\n"
        "  callback = reload_everything,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'o', '', {{\n"
        "  callback = open_current_item,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'a', '', {{\n"
        "  callback = add_current_item,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'x', '', {{\n"
        "  callback = cancel_current_item,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "vim.api.nvim_buf_set_keymap(0, 'n', 'pp', '', {{\n"
        "  callback = function()\n"
        "    vim.notify('Publishing...', vim.log.levels.INFO)\n"
        "    local result = vim.fn.system({{'gg', 'pr', '_publish', tostring(pr_id)}})\n"
        "    local ok, data = pcall(vim.fn.json_decode, result)\n"
        "    if ok then\n"
        "      if data.status == 'ok' then\n"
        "        sync_view()\n"
        "        vim.notify('PR published successfully', vim.log.levels.INFO)\n"
        "      elseif data.status == 'no_changes' then\n"
        "        vim.notify('No changes to publish', vim.log.levels.INFO)\n"
        "      else\n"
        "        vim.notify('Publish failed: ' .. tostring(data.message), vim.log.levels.ERROR)\n"
        "      end\n"
        "    else\n"
        "      vim.notify('Publish failed: ' .. tostring(result), vim.log.levels.ERROR)\n"
        "    end\n"
        "  end,\n"
        "  noremap = true,\n"
        "  silent = true,\n"
        "}})\n"
        "\n"
        "sync_view()\n"
    ).format(pr_id=pr_id, manage_path=manage_path, cache_dir=cache_dir)


_RESOURCE = "https://app.vssps.visualstudio.com"


def cmd_pr_manage(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    os.makedirs(cache_dir, exist_ok=True)

    pr_path = os.path.join(cache_dir, "pr.json")
    manage_path = os.path.join(cache_dir, "manage.md")

    print(f"Fetching PR {pr_id}...", file=sys.stderr)
    result = _run_az(f"az repos pr show --id {pr_id} --output json")
    if result.returncode != 0:
        print(f"Failed to fetch PR: {result.stderr}", file=sys.stderr)
        return 1

    pr = json.loads(result.stdout)

    for stale in (
        "summary.md",
        "status.txt",
        "vote.txt",
        "changes.log",
        "threads.log",
        "policies.log",
    ):
        stale_path = os.path.join(cache_dir, stale)
        if os.path.isfile(stale_path):
            os.unlink(stale_path)

    with open(pr_path, "w") as f:
        json.dump(pr, f)

    content = _format_manage_content(pr, cache_dir)
    with open(manage_path, "w") as f:
        f.write(content)

    lua_code = _get_manage_lua(pr_id, manage_path, cache_dir)
    lua_path = os.path.join(cache_dir, "manage.lua")
    with open(lua_path, "w") as f:
        f.write(lua_code)

    subprocess.run(["nvim", manage_path, "-c", f"luafile {shlex.quote(lua_path)}"])

    return 0


def cmd_pr_fetch_summary(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")
    summary_path = os.path.join(cache_dir, "summary.md")

    if not os.path.isfile(pr_path):
        result = _run_az(f"az repos pr show --id {pr_id} --output json")
        if result.returncode != 0:
            print(json.dumps({"status": "error", "message": "failed to fetch PR"}))
            return 1
        os.makedirs(cache_dir, exist_ok=True)
        with open(pr_path, "w") as f:
            f.write(result.stdout)

    with open(pr_path) as f:
        pr = json.load(f)

    created = False
    if not os.path.isfile(summary_path):
        title = pr.get("title", "")
        description = pr.get("description") or ""
        with open(summary_path, "w") as f:
            f.write(f"{title}\n")
            if description:
                f.write(f"{description}\n")
        created = True

    print(json.dumps({"status": "ok", "path": summary_path, "created": created}))
    return 0


def cmd_pr_publish_data(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")
    summary_path = os.path.join(cache_dir, "summary.md")
    status_path = os.path.join(cache_dir, "status.txt")
    vote_path = os.path.join(cache_dir, "vote.txt")

    with open(pr_path) as f:
        pr = json.load(f)

    has_changes = False
    body = {}
    pending_responses = _pending_thread_responses(cache_dir)
    pending_thread_statuses = _pending_thread_status_changes(cache_dir)
    pending_new_threads = _pending_new_thread_drafts(cache_dir)
    pending_vote = ""
    if os.path.isfile(vote_path):
        with open(vote_path) as f:
            pending_vote = f.read().strip()

    if os.path.isfile(summary_path):
        with open(summary_path) as f:
            content = f.read().strip()
        if content:
            lines = content.split("\n", 1)
            new_title = lines[0].strip()
            new_description = lines[1].strip() if len(lines) > 1 else ""
            original_title = pr.get("title", "")
            original_description = pr.get("description") or ""
            if (new_title, new_description) != (original_title, original_description):
                body["title"] = new_title
                body["description"] = new_description
                has_changes = True

    if os.path.isfile(status_path):
        with open(status_path) as f:
            new_status = f.read().strip()
        original_status = _get_pr_status_label(pr)
        if new_status != original_status:
            body.update(_status_to_api_body(new_status))
            has_changes = True

    if (
        not has_changes
        and not pending_responses
        and not pending_thread_statuses
        and not pending_new_threads
        and not pending_vote
    ):
        print(json.dumps({"status": "no_changes"}))
        return 0

    if pending_vote and pending_vote not in VOTE_ACTIONS:
        print(
            json.dumps({"status": "error", "message": f"invalid vote: {pending_vote}"})
        )
        return 1

    if has_changes:
        fd, body_path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(body, f)

        api_url = pr["url"]
        if "api-version" not in api_url:
            api_url += "?api-version=7.1"

        cmd = (
            f"az rest --method PATCH --url {shlex.quote(api_url)} "
            f"--body @{shlex.quote(body_path)} "
            f"--headers Content-Type=application/json "
            f"--resource {_RESOURCE}"
        )
        result = _run_az(cmd)
        os.unlink(body_path)

        if result.returncode != 0:
            print(json.dumps({"status": "error", "message": result.stderr.strip()}))
            return 1

        if "title" in body:
            pr["title"] = body["title"]
        if "description" in body:
            pr["description"] = body["description"]
        if "isDraft" in body:
            pr["isDraft"] = body["isDraft"]
        if "status" in body:
            pr["status"] = body["status"]

        with open(pr_path, "w") as f:
            json.dump(pr, f)

        if os.path.isfile(status_path):
            os.unlink(status_path)

    updated_vote = ""
    if pending_vote:
        result = _update_reviewer_vote(pr, pending_vote)
        if result.returncode != 0:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"failed to update vote: {result.stderr.strip() or result.stdout.strip()}",
                    }
                )
            )
            return 1
        _apply_vote_to_cached_pr(pr, pending_vote)
        with open(pr_path, "w") as f:
            json.dump(pr, f)
        if os.path.isfile(vote_path):
            os.unlink(vote_path)
        updated_vote = pending_vote

    updated_thread_statuses = []
    for thread_id, draft in pending_thread_statuses.items():
        result = _patch_thread_status(pr, thread_id, draft["status"])
        if result.returncode != 0:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"failed to update status for thread {thread_id}: {result.stderr.strip() or result.stdout.strip()}",
                    }
                )
            )
            return 1
        if thread_id not in pending_responses and os.path.isfile(draft["path"]):
            os.unlink(draft["path"])
        updated_thread_statuses.append(thread_id)

    posted_threads = []
    for thread_id, draft in pending_responses.items():
        result = _post_thread_response(pr, thread_id, draft["response"])
        if result.returncode != 0:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"failed to post response to thread {thread_id}: {result.stderr.strip() or result.stdout.strip()}",
                    }
                )
            )
            return 1
        if os.path.isfile(draft["path"]):
            os.unlink(draft["path"])
        posted_threads.append(thread_id)

    if updated_thread_statuses or posted_threads:
        threads_path = os.path.join(cache_dir, "threads.json")
        if os.path.isfile(threads_path):
            os.unlink(threads_path)

    posted_new_threads = []
    for draft_id, draft in pending_new_threads.items():
        result = _post_new_thread(pr, draft)
        if result.returncode != 0:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": f"failed to post new thread {draft_id}: {result.stderr.strip() or result.stdout.strip()}",
                    }
                )
            )
            return 1
        os.unlink(draft["path"])
        posted_new_threads.append(draft_id)

    if posted_new_threads:
        threads_path = os.path.join(cache_dir, "threads.json")
        if os.path.isfile(threads_path):
            os.unlink(threads_path)

    print(
        json.dumps(
            {
                "status": "ok",
                "posted_threads": posted_threads,
                "updated_thread_statuses": updated_thread_statuses,
                "posted_new_threads": posted_new_threads,
                "updated_vote": updated_vote,
            }
        )
    )
    return 0


def cmd_pr_set_status(args):
    pr_id = args.pr_id
    new_status = args.status

    if new_status not in PR_STATUSES:
        print(
            json.dumps({"status": "error", "message": f"invalid status: {new_status}"})
        )
        return 1

    cache_dir = _get_cache_dir(pr_id)
    os.makedirs(cache_dir, exist_ok=True)
    status_path = os.path.join(cache_dir, "status.txt")

    with open(status_path, "w") as f:
        f.write(new_status)

    print(json.dumps({"status": "ok", "new_status": new_status}))
    return 0


def cmd_pr_set_vote(args):
    pr_id = args.pr_id
    action = args.vote

    if action not in VOTE_ACTIONS:
        print(json.dumps({"status": "error", "message": f"invalid vote: {action}"}))
        return 1

    cache_dir = _get_cache_dir(pr_id)
    os.makedirs(cache_dir, exist_ok=True)
    vote_path = os.path.join(cache_dir, "vote.txt")

    with open(vote_path, "w") as f:
        f.write(action)

    print(json.dumps({"status": "ok", "new_vote": action}))
    return 0


def cmd_pr_manage_sync(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")
    summary_path = os.path.join(cache_dir, "summary.md")

    if not os.path.isfile(pr_path):
        print(json.dumps({"status": "error", "message": "pr.json not found"}))
        return 1

    with open(pr_path) as f:
        pr = json.load(f)

    original_title = pr.get("title", "")
    original_description = pr.get("description") or ""

    summary_exists = os.path.isfile(summary_path)
    current_title = original_title
    current_description = original_description

    if summary_exists:
        with open(summary_path) as f:
            content = f.read()
        lines = content.split("\n", 1)
        current_title = lines[0].strip()
        desc = lines[1].strip() if len(lines) > 1 else ""
        if desc == "":
            current_description = ""
        else:
            current_description = desc

    changed = (current_title, current_description) != (
        original_title,
        original_description,
    )
    desc_lines = current_description.split("\n") if current_description else []

    status_path = os.path.join(cache_dir, "status.txt")
    vote_path = os.path.join(cache_dir, "vote.txt")
    original_status = _get_pr_status_label(pr)
    current_status = original_status
    if os.path.isfile(status_path):
        with open(status_path) as f:
            current_status = f.read().strip()
    status_changed = current_status != original_status
    pending_vote = ""
    if os.path.isfile(vote_path):
        with open(vote_path) as f:
            pending_vote = f.read().strip()
    vote_changed = pending_vote in VOTE_ACTIONS

    pending_thread_ids = sorted(_pending_thread_responses(cache_dir).keys(), key=int)
    pending_thread_status_changes = _pending_thread_status_changes(cache_dir)
    pending_thread_status_ids = sorted(pending_thread_status_changes.keys(), key=int)
    pending_thread_statuses = {
        thread_id: draft["status"]
        for thread_id, draft in pending_thread_status_changes.items()
    }
    thread_responses_changed = bool(pending_thread_ids)
    thread_statuses_changed = bool(pending_thread_status_ids)
    pending_new_threads = _new_thread_drafts_for_manage(cache_dir)
    new_threads_changed = any(t["has_comment"] for t in pending_new_threads)

    print(
        json.dumps(
            {
                "status": "ok",
                "title": current_title,
                "description_lines": desc_lines,
                "reviewer_lines": _format_manage_reviewer_lines(pr),
                "changed": changed,
                "pr_status": current_status,
                "original_status": original_status,
                "status_changed": status_changed,
                "vote_changed": vote_changed,
                "pending_vote": pending_vote if vote_changed else "",
                "pending_vote_label": VOTE_ACTIONS[pending_vote]["label"]
                if vote_changed
                else "",
                "pending_thread_ids": pending_thread_ids,
                "pending_thread_status_ids": pending_thread_status_ids,
                "pending_thread_statuses": pending_thread_statuses,
                "thread_responses_changed": thread_responses_changed,
                "thread_statuses_changed": thread_statuses_changed,
                "pending_new_threads": pending_new_threads,
                "new_threads_changed": new_threads_changed,
            }
        )
    )
    return 0


def cmd_pr_manage_reload(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")

    result = _run_az(f"az repos pr show --id {pr_id} --output json")
    if result.returncode != 0:
        print(json.dumps({"status": "error", "message": result.stderr.strip()}))
        return 1

    os.makedirs(cache_dir, exist_ok=True)
    with open(pr_path, "w") as f:
        f.write(result.stdout)

    for stale in ("summary.md", "status.txt", "vote.txt"):
        stale_path = os.path.join(cache_dir, stale)
        if os.path.isfile(stale_path):
            os.unlink(stale_path)

    print(json.dumps({"status": "ok"}))
    return 0


def _get_pr_repository_id(pr):
    repository = pr.get("repository")
    if isinstance(repository, dict) and repository.get("id"):
        return repository["id"]
    if pr.get("repositoryId"):
        return pr["repositoryId"]
    match = re.search(r"/repositories/([^/]+)/pullRequests/", pr.get("url", ""))
    if match:
        return match.group(1)
    return ""


def _get_pr_project_name_or_id(pr):
    repository = pr.get("repository")
    if isinstance(repository, dict):
        project = repository.get("project")
        if isinstance(project, dict):
            return project.get("name") or project.get("id") or ""
    return _ado_project_from_pr_url(pr)


def _favorite_pr_branch(pr, branch, log=None):
    org = _ado_org_from_pr_url(pr)
    project = _get_pr_project_name_or_id(pr)
    repo_id = _get_pr_repository_id(pr)
    if not org or not project or not repo_id or not branch:
        if log:
            log("Skipping source branch favorite: missing org/project/repository metadata")
        return None

    endpoint = (
        f"https://dev.azure.com/{org}/{project}/_apis/git/favorites/refs"
        "?api-version=7.1"
    )
    ref_name = branch if branch.startswith("refs/") else f"refs/heads/{branch}"
    fd, body_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(
            {
                "name": ref_name,
                "repositoryId": repo_id,
                "type": "ref",
            },
            f,
        )
    try:
        result = _run_az(
            f"az rest --method POST --url {shlex.quote(endpoint)} "
            f"--body @{shlex.quote(body_path)} "
            f"--headers Content-Type=application/json "
            f"--resource {_RESOURCE}"
        )
    finally:
        os.unlink(body_path)

    if log:
        log(
            "favorite source branch: "
            f"rc={result.returncode} stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}"
        )
    return result


def cmd_pr_manage_changes(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")
    log_path = os.path.join(cache_dir, "changes.log")

    def _log(msg):
        with open(log_path, "a") as lf:
            lf.write(f"{msg}\n")

    _log(f"=== manage-changes start pr={pr_id} ===")

    if not os.path.isfile(pr_path):
        _log("ERROR: pr.json not found")
        print(json.dumps({"status": "error", "message": "pr.json not found"}))
        return 1

    with open(pr_path) as f:
        pr = json.load(f)

    source = pr.get("sourceRefName", "").removeprefix("refs/heads/")
    target = pr.get("targetRefName", "").removeprefix("refs/heads/")
    _log(f"source={source} target={target}")

    _favorite_pr_branch(pr, source, _log)

    _log(f"Fetching origin/{source} origin/{target}")
    fetch_result = run(["git", "fetch", "origin", source, target])
    _log(
        f"fetch: rc={fetch_result.returncode} stdout={fetch_result.stdout.strip()!r} stderr={fetch_result.stderr.strip()!r}"
    )
    if fetch_result.returncode != 0:
        _log(f"ERROR: git fetch failed")
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"git fetch failed: {fetch_result.stderr.strip()}",
                }
            )
        )
        return 1

    diff_spec = f"origin/{target}...origin/{source}"
    _log(f"diff_spec={diff_spec}")

    name_status_result = run(["git", "diff", "--name-status", diff_spec])
    _log(
        f"name-status: rc={name_status_result.returncode} stdout={name_status_result.stdout.strip()!r} stderr={name_status_result.stderr.strip()!r}"
    )
    if name_status_result.returncode != 0:
        _log(f"ERROR: git diff --name-status failed")
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"git diff --name-status failed: {name_status_result.stderr.strip()}",
                }
            )
        )
        return 1

    numstat_result = run(["git", "diff", "--numstat", diff_spec])
    _log(
        f"numstat: rc={numstat_result.returncode} stdout={numstat_result.stdout.strip()!r} stderr={numstat_result.stderr.strip()!r}"
    )
    if numstat_result.returncode != 0:
        _log(f"ERROR: git diff --numstat failed")
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"git diff --numstat failed: {numstat_result.stderr.strip()}",
                }
            )
        )
        return 1

    name_status_lines = (
        name_status_result.stdout.strip().split("\n")
        if name_status_result.stdout.strip()
        else []
    )
    numstat_lines = (
        numstat_result.stdout.strip().split("\n")
        if numstat_result.stdout.strip()
        else []
    )

    files = []
    total_added = 0
    total_deleted = 0

    for i, name_line in enumerate(name_status_lines):
        if not name_line:
            continue
        parts = name_line.split(None, 1)
        if len(parts) < 2:
            continue
        status_code = parts[0]
        filename = parts[1]

        added = 0
        deleted = 0
        if i < len(numstat_lines) and numstat_lines[i]:
            num_parts = numstat_lines[i].split("\t")
            if len(num_parts) >= 2:
                if num_parts[0] != "-":
                    added = int(num_parts[0])
                if num_parts[1] != "-":
                    deleted = int(num_parts[1])

        total_added += added
        total_deleted += deleted
        files.append(
            {
                "status": status_code,
                "filename": filename,
                "added": added,
                "deleted": deleted,
            }
        )

    changes = {
        "files": files,
        "total_files": len(files),
        "total_added": total_added,
        "total_deleted": total_deleted,
    }

    changes_path = os.path.join(cache_dir, "changes.json")
    with open(changes_path, "w") as f:
        json.dump(changes, f)

    print(json.dumps({"status": "ok", **changes}))
    return 0


def _load_raw_threads(cache_dir):
    threads_path = os.path.join(cache_dir, "threads.json")
    if not os.path.isfile(threads_path):
        return []
    with open(threads_path) as f:
        data = json.load(f)
    return _raw_threads_from_cache(data)


def _find_raw_thread(cache_dir, thread_id):
    for thread in _load_raw_threads(cache_dir):
        if str(thread.get("id", "")) == str(thread_id):
            return thread
    return None


def _get_manage_diff_for_thread(pr):
    return _get_manage_diff(pr)


def _get_manage_diff(pr):
    source = pr.get("sourceRefName", "").removeprefix("refs/heads/")
    target = pr.get("targetRefName", "").removeprefix("refs/heads/")
    if not source or not target:
        return ""
    result = run(["git", "diff", f"origin/{target}...origin/{source}"])
    if result.returncode != 0:
        return ""
    return result.stdout


def _parse_diff_git_paths(line):
    match = re.match(r"^diff --git a/(.+) b/(.+)$", line)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _build_diff_line_index(full_diff):
    hunk_header = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    result = {}
    old_path = None
    new_path = None
    old_line = None
    new_line = None

    for diff_line, line in enumerate(full_diff.splitlines(), start=1):
        if line.startswith("diff --git "):
            old_path, new_path = _parse_diff_git_paths(line)
            old_line = None
            new_line = None
            continue

        if old_path is None or new_path is None:
            continue

        match = hunk_header.match(line)
        if match:
            old_line = int(match.group(1))
            new_line = int(match.group(2))
            continue

        if old_line is None or new_line is None or line.startswith("\\"):
            continue

        marker = line[:1]
        if marker == "+":
            if not line.startswith("+++"):
                result[(new_path, "right", new_line)] = diff_line
                new_line += 1
        elif marker == "-":
            if not line.startswith("---"):
                result[(old_path, "left", old_line)] = diff_line
                old_line += 1
        else:
            result[(new_path, "right", new_line)] = diff_line
            result[(old_path, "left", old_line)] = diff_line
            old_line += 1
            new_line += 1

    return result


def _build_diff_line_map(full_diff):
    hunk_header = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    result = {}
    old_path = None
    new_path = None
    old_line = None
    new_line = None

    for diff_line, line in enumerate(full_diff.splitlines(), start=1):
        if line.startswith("diff --git "):
            old_path, new_path = _parse_diff_git_paths(line)
            old_line = None
            new_line = None
            continue

        if old_path is None or new_path is None:
            continue

        match = hunk_header.match(line)
        if match:
            old_line = int(match.group(1))
            new_line = int(match.group(2))
            continue

        if old_line is None or new_line is None or line.startswith("\\"):
            continue

        marker = line[:1]
        if marker == "+":
            if not line.startswith("+++"):
                result[str(diff_line)] = {
                    "file_path": f"/{new_path}",
                    "side": "right",
                    "line": new_line,
                }
                new_line += 1
        elif marker == "-":
            if not line.startswith("---"):
                result[str(diff_line)] = {
                    "file_path": f"/{old_path}",
                    "side": "left",
                    "line": old_line,
                }
                old_line += 1
        else:
            result[str(diff_line)] = {
                "file_path": f"/{new_path}",
                "side": "right",
                "line": new_line,
            }
            old_line += 1
            new_line += 1

    return result


def _diff_thread_annotations(full_diff, raw_threads):
    line_index = _build_diff_line_index(full_diff)
    annotations = []
    for thread in raw_threads:
        if _is_system_thread(thread):
            continue
        first = _first_display_comment(thread)
        if first is None:
            continue

        ctx = thread.get("threadContext") or {}
        file_path = _normalize_thread_file_path(ctx.get("filePath", ""))
        if not file_path:
            continue

        right_start = ctx.get("rightFileStart") or {}
        left_start = ctx.get("leftFileStart") or {}
        diff_line = None
        file_line = right_start.get("line")
        side = "right"
        if file_line:
            diff_line = line_index.get((file_path, "right", file_line))
        if diff_line is None and left_start.get("line"):
            file_line = left_start.get("line")
            side = "left"
            diff_line = line_index.get((file_path, "left", file_line))
        if diff_line is None:
            continue

        annotations.append(
            {
                "thread_id": thread.get("id", ""),
                "status": thread.get("status", ""),
                "file_path": file_path,
                "file_line": file_line,
                "side": side,
                "diff_line": diff_line,
                "author": first.get("author", {}).get("uniqueName", ""),
                "preview": _sanitize_thread_preview(first.get("content", ""), 80),
            }
        )
    return annotations


def _diff_view_path(cache_dir):
    return os.path.join(cache_dir, "diff.diff")


def _write_manage_diff_file(cache_dir, pr):
    full_diff = _get_manage_diff(pr)
    if not full_diff:
        return "", [], {}
    path = _diff_view_path(cache_dir)
    with open(path, "w") as f:
        f.write(full_diff)
        if not full_diff.endswith("\n"):
            f.write("\n")
    return (
        path,
        _diff_thread_annotations(full_diff, _load_raw_threads(cache_dir)),
        _build_diff_line_map(full_diff),
    )


def _write_new_thread_file(cache_dir, file_path="", side="", line=None):
    draft_id = f"new-{uuid.uuid4().hex[:12]}"
    path = _new_thread_draft_path(cache_dir, draft_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    normalized_file = ""
    if file_path:
        normalized_file = "/" + _normalize_thread_file_path(file_path)
    normalized_side = side if side in ("left", "right") else ""
    normalized_line = int(line) if line is not None else None

    with open(path, "w") as f:
        f.write("---\n")
        f.write("kind: new-thread\n")
        f.write(f"draft_id: {draft_id}\n")
        f.write("status: active\n")
        if normalized_file and normalized_side and normalized_line:
            f.write(f"file_path: {normalized_file}\n")
            f.write(f"side: {normalized_side}\n")
            f.write(f"line: {normalized_line}\n")
        f.write("---\n\n")
        if normalized_file and normalized_side and normalized_line:
            f.write(f"Location: {normalized_file}:{normalized_line} ({normalized_side})\n\n")
        else:
            f.write("Location: general PR thread\n\n")
        f.write("# Comment\n\n")
        f.write(f"{NEW_THREAD_COMMENT_MARKER}\n")
        f.write(f"{NEW_THREAD_COMMENT_PLACEHOLDER}\n")

    return path, draft_id


def _write_manage_thread_file(cache_dir, pr, thread):
    thread_id = thread.get("id", "")
    path = _thread_draft_path(cache_dir, thread_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path) and _read_thread_response(path):
        return path, False

    comments = thread.get("comments") or []
    thread_context = thread.get("threadContext") or {}
    file_path = thread_context.get("filePath", "")
    location_line = (thread_context.get("rightFileStart") or {}).get("line")
    first = _first_display_comment(thread) or (comments[0] if comments else {})
    first_author = first.get("author", {}).get("uniqueName", "")

    hunk = ""
    if file_path:
        start = (thread_context.get("rightFileStart") or {}).get("line")
        end = (thread_context.get("rightFileEnd") or {}).get("line")
        hunk = _get_file_hunks(_get_manage_diff_for_thread(pr), file_path, start, end)

    with open(path, "w") as f:
        f.write("---\n")
        f.write(f"id: {thread_id}\n")
        if first_author:
            f.write(f"author: {first_author}\n")
        if file_path:
            location = f"{file_path}:{location_line}" if location_line else file_path
            f.write(f"location: {location}\n")
        f.write(f"status: {thread.get('status', '')}\n")
        f.write("---\n\n")

        if hunk:
            f.write(f"```diff\n{hunk}\n```\n\n")

        f.write("# Comments\n\n")
        for comment in comments:
            content = comment.get("content", "")
            if not content or _is_only_marker_content(content):
                continue
            author = comment.get("author", {}).get("uniqueName", "")
            date = _format_thread_date(comment.get("publishedDate", ""))
            heading = " ".join(part for part in (author, date) if part)
            f.write(f"## {heading}\n\n{content}\n\n")

        f.write("# Response\n\n")
        f.write(f"{THREAD_RESPONSE_MARKER}\n")
        f.write(f"{THREAD_RESPONSE_PLACEHOLDER}\n")

    return path, True


def _set_manage_thread_status(cache_dir, pr, thread_id, status):
    if status not in THREAD_STATUSES:
        raise ValueError(f"invalid status: {status}")
    if str(thread_id).startswith("new-"):
        path = _new_thread_draft_path(cache_dir, thread_id)
        if not os.path.isfile(path):
            raise ValueError(f"thread draft {thread_id} not found")
        if not _replace_frontmatter_value(path, "status", status):
            raise ValueError(f"failed to update status in {path}")
        return path
    thread = _find_raw_thread(cache_dir, thread_id)
    if thread is None:
        raise ValueError(f"thread {thread_id} not found; press r on Threads to refresh")
    path, _ = _write_manage_thread_file(cache_dir, pr, thread)
    if not _replace_frontmatter_value(path, "status", status):
        raise ValueError(f"failed to update status in {path}")
    return path


def _patch_thread_status(pr, thread_id, status):
    thread_url = f"{pr['url']}/threads/{thread_id}?api-version=7.1"
    fd, body_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"status": status}, f)
    cmd = (
        f"az rest --method PATCH --url {shlex.quote(thread_url)} "
        f"--body @{shlex.quote(body_path)} "
        f"--headers Content-Type=application/json "
        f"--resource {_RESOURCE}"
    )
    result = _run_az(cmd)
    os.unlink(body_path)
    return result


def _post_thread_response(pr, thread_id, response):
    comment_url = f"{pr['url']}/threads/{thread_id}/comments?api-version=7.1"
    fd, body_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"content": response, "commentType": "text"}, f)
    cmd = (
        f"az rest --method POST --url {shlex.quote(comment_url)} "
        f"--body @{shlex.quote(body_path)} "
        f"--headers Content-Type=application/json "
        f"--resource {_RESOURCE}"
    )
    result = _run_az(cmd)
    os.unlink(body_path)
    return result


def _post_new_thread(pr, draft):
    body = {
        "comments": [
            {
                "parentCommentId": 0,
                "content": draft["comment"],
                "commentType": "text",
            }
        ],
        "status": draft.get("status") if draft.get("status") in THREAD_STATUSES else "active",
    }

    file_path = draft.get("file_path", "")
    side = draft.get("side", "")
    line_text = draft.get("line", "")
    if file_path and side in ("left", "right") and line_text:
        line = int(line_text)
        line_position = {"line": line, "offset": 1}
        context = {"filePath": file_path}
        if side == "left":
            context["leftFileStart"] = line_position
            context["leftFileEnd"] = line_position
        else:
            context["rightFileStart"] = line_position
            context["rightFileEnd"] = line_position
        body["threadContext"] = context

    thread_url = f"{pr['url']}/threads?api-version=7.1"
    fd, body_path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(body, f)
    cmd = (
        f"az rest --method POST --url {shlex.quote(thread_url)} "
        f"--body @{shlex.quote(body_path)} "
        f"--headers Content-Type=application/json "
        f"--resource {_RESOURCE}"
    )
    result = _run_az(cmd)
    os.unlink(body_path)
    return result


def cmd_pr_manage_thread_open(args):
    pr_id = args.pr_id
    thread_id = args.thread_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")

    if not os.path.isfile(pr_path):
        print(json.dumps({"status": "error", "message": "pr.json not found"}))
        return 1

    try:
        with open(pr_path) as f:
            pr = json.load(f)
        thread = _find_raw_thread(cache_dir, thread_id)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1

    if thread is None:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"thread {thread_id} not found; press r on Threads to refresh",
                }
            )
        )
        return 1

    path, created = _write_manage_thread_file(cache_dir, pr, thread)
    print(json.dumps({"status": "ok", "path": path, "created": created}))
    return 0


def cmd_pr_manage_thread_status(args):
    pr_id = args.pr_id
    thread_id = args.thread_id
    status = args.status
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")

    if not os.path.isfile(pr_path):
        print(json.dumps({"status": "error", "message": "pr.json not found"}))
        return 1

    try:
        with open(pr_path) as f:
            pr = json.load(f)
        path = _set_manage_thread_status(cache_dir, pr, thread_id, status)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1

    print(json.dumps({"status": "ok", "path": path, "thread_status": status}))
    return 0


def cmd_pr_manage_diff_open(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")

    if not os.path.isfile(pr_path):
        print(json.dumps({"status": "error", "message": "pr.json not found"}))
        return 1

    try:
        with open(pr_path) as f:
            pr = json.load(f)
        path, annotations, line_map = _write_manage_diff_file(cache_dir, pr)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1

    if not path:
        print(json.dumps({"status": "error", "message": "git diff failed or was empty"}))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "path": path,
                "annotations": annotations,
                "line_map": line_map,
            }
        )
    )
    return 0


def cmd_pr_manage_thread_new(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")

    if not os.path.isfile(pr_path):
        print(json.dumps({"status": "error", "message": "pr.json not found"}))
        return 1

    if bool(args.file_path) != bool(args.side and args.line):
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "file path, side, and line must be provided together",
                }
            )
        )
        return 1

    path, draft_id = _write_new_thread_file(
        cache_dir,
        file_path=args.file_path or "",
        side=args.side or "",
        line=args.line,
    )
    print(json.dumps({"status": "ok", "path": path, "draft_id": draft_id}))
    return 0


def cmd_pr_manage_threads(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    pr_path = os.path.join(cache_dir, "pr.json")
    log_path = os.path.join(cache_dir, "threads.log")

    def _log(msg):
        with open(log_path, "a") as lf:
            lf.write(f"{msg}\n")

    _log(f"=== manage-threads start pr={pr_id} ===")

    if not os.path.isfile(pr_path):
        _log("ERROR: pr.json not found")
        print(json.dumps({"status": "error", "message": "pr.json not found"}))
        return 1

    with open(pr_path) as f:
        pr = json.load(f)

    thread_url = pr.get("url", "") + "/threads?api-version=7.1"
    if not thread_url.startswith("http"):
        _log("ERROR: thread URL not found")
        print(json.dumps({"status": "error", "message": "thread URL not found"}))
        return 1

    result = _run_az(
        f"az rest --url {shlex.quote(thread_url)} --resource {_RESOURCE} --output json",
        timeout=60,
    )
    _log(
        f"az rest: rc={result.returncode} stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}"
    )
    if result.returncode != 0:
        _log("ERROR: thread fetch failed")
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"thread fetch failed: {result.stderr.strip()}",
                }
            )
        )
        return 1

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        _log(f"ERROR: failed to parse threads JSON: {exc}")
        print(json.dumps({"status": "error", "message": "failed to parse threads JSON"}))
        return 1

    raw_threads = data.get("value", data if isinstance(data, list) else [])
    threads = _format_threads_for_manage(raw_threads)
    payload = {
        "threads": threads,
        "total_threads": len(threads),
    }

    threads_path = os.path.join(cache_dir, "threads.json")
    with open(threads_path, "w") as f:
        json.dump(data, f)

    print(json.dumps({"status": "ok", **payload}))
    return 0


def cmd_pr_manage_policies(args):
    pr_id = args.pr_id
    cache_dir = _get_cache_dir(pr_id)
    os.makedirs(cache_dir, exist_ok=True)
    log_path = os.path.join(cache_dir, "policies.log")

    def _log(msg):
        with open(log_path, "a") as lf:
            lf.write(f"{msg}\n")

    _log(f"=== manage-policies start pr={pr_id} ===")

    result = _run_az(f"az repos pr policy list --id {pr_id} --output json", timeout=60)
    _log(
        f"az policy list: rc={result.returncode} stdout_len={len(result.stdout)} stderr={result.stderr.strip()!r}"
    )
    if result.returncode != 0:
        _log("ERROR: policy fetch failed")
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"policy fetch failed: {result.stderr.strip()}",
                }
            )
        )
        return 1

    try:
        raw_policies = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        _log(f"ERROR: failed to parse policies JSON: {exc}")
        print(json.dumps({"status": "error", "message": "failed to parse policies JSON"}))
        return 1

    policies = _format_policies_for_manage(raw_policies)
    payload = {
        "policies": policies,
        "total_policies": len(policies),
    }

    policies_path = os.path.join(cache_dir, "policies.json")
    with open(policies_path, "w") as f:
        json.dump(raw_policies, f)

    print(json.dumps({"status": "ok", **payload}))
    return 0


def cmd_pr_manage_policy_queue(args):
    pr_id = args.pr_id
    policy_id = args.policy_id
    cache_dir = _get_cache_dir(pr_id)
    os.makedirs(cache_dir, exist_ok=True)
    log_path = os.path.join(cache_dir, "policies.log")

    def _log(msg):
        with open(log_path, "a") as lf:
            lf.write(f"{msg}\n")

    _log(f"=== manage-policy-queue start pr={pr_id} policy_id={policy_id} ===")
    policies_path = os.path.join(cache_dir, "policies.json")

    def _resolve_evaluation_id(raw_policies):
        if not isinstance(raw_policies, list):
            return ""
        for policy in raw_policies:
            cfg = policy.get("configuration", {})
            if str(cfg.get("id", "")) == str(policy_id):
                return policy.get("evaluationId", "")
        return ""

    if not os.path.isfile(policies_path):
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "policies.json not found; press r on Policies to refresh",
                }
            )
        )
        return 1

    try:
        with open(policies_path) as f:
            raw_policies = json.load(f)
    except json.JSONDecodeError:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "failed to parse policies.json; press r on Policies to refresh",
                }
            )
        )
        return 1

    evaluation_id = _resolve_evaluation_id(raw_policies)

    if not evaluation_id:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"evaluation id not found for policy {policy_id}; press r on Policies to refresh",
                }
            )
        )
        return 1

    result = _run_az(
        f"az repos pr policy queue --id {pr_id} --evaluation-id {shlex.quote(evaluation_id)} --output json",
        timeout=60,
    )
    _log(
        f"az policy queue: rc={result.returncode} stdout_len={len(result.stdout)} stderr={result.stderr.strip()!r}"
    )
    if result.returncode != 0:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": result.stderr.strip() or result.stdout.strip(),
                }
            )
        )
        return 1

    print(json.dumps({"status": "ok"}))
    return 0


def cmd_pr_manage_policy_cancel(args):
    pr_id = args.pr_id
    policy_id = args.policy_id
    cache_dir = _get_cache_dir(pr_id)
    os.makedirs(cache_dir, exist_ok=True)
    log_path = os.path.join(cache_dir, "policies.log")

    def _log(msg):
        with open(log_path, "a") as lf:
            lf.write(f"{msg}\n")

    _log(f"=== manage-policy-cancel start pr={pr_id} policy_id={policy_id} ===")
    policies_path = os.path.join(cache_dir, "policies.json")

    def _resolve_build_id(raw_policies):
        if not isinstance(raw_policies, list):
            return ""
        for policy in raw_policies:
            cfg = policy.get("configuration", {})
            if str(cfg.get("id", "")) == str(policy_id):
                ctx = policy.get("context") or {}
                return ctx.get("buildId", "")
        return ""

    if not os.path.isfile(policies_path):
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "policies.json not found; press r on Policies to refresh",
                }
            )
        )
        return 1

    try:
        with open(policies_path) as f:
            raw_policies = json.load(f)
    except json.JSONDecodeError:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "failed to parse policies.json; press r on Policies to refresh",
                }
            )
        )
        return 1

    build_id = _resolve_build_id(raw_policies)
    if not build_id:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": f"build id not found for policy {policy_id}; press r on Policies to refresh",
                }
            )
        )
        return 1

    result = _run_az(
        f"az pipelines build cancel --build-id {shlex.quote(str(build_id))} --output json",
        timeout=60,
    )
    _log(
        f"az build cancel: rc={result.returncode} build_id={build_id} stdout_len={len(result.stdout)} stderr={result.stderr.strip()!r}"
    )
    if result.returncode != 0:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": result.stderr.strip() or result.stdout.strip(),
                }
            )
        )
        return 1

    print(json.dumps({"status": "ok", "build_id": build_id}))
    return 0


def cmd_pr_list(args):
    if args.review or not args.all_prs:
        email = _get_git_email()
        if email is None:
            return 1
        email_local = email.split("@")[0] if "@" in email else None
    else:
        email = None
        email_local = None

    if args.review:
        cmd = f"az repos pr list --reviewer {shlex.quote(email)} --status active --output json"
    elif args.all_prs:
        cmd = "az repos pr list --status active --output json"
    else:
        cmd = f"az repos pr list --creator {shlex.quote(email)} --status active --output json"

    result = _run_az(cmd)
    if result.returncode != 0:
        print(f"az command failed: {result.stderr}", file=sys.stderr)
        return 1

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Failed to parse az output as JSON.", file=sys.stderr)
        return 1

    if not prs:
        return 0

    id_width = max(len(str(pr["pullRequestId"])) for pr in prs)

    TITLE_MAX = 60

    for pr in prs:
        pr_id = pr["pullRequestId"]
        title = pr["title"]
        branch = pr.get("sourceRefName", "").removeprefix("refs/heads/")
        if email_local and branch.startswith(f"user/{email_local}/"):
            branch = branch.removeprefix(f"user/{email_local}/")
        reviewers = pr.get("reviewers") or []

        required = [r for r in reviewers if r.get("isRequired")]
        approved = sum(1 for r in required if r.get("vote", 0) >= 5)
        blocked = sum(1 for r in required if r.get("vote") == -5)
        novote = sum(1 for r in required if r.get("vote", 0) == 0)

        if len(title) > TITLE_MAX:
            title = title[: TITLE_MAX - 1] + "\u2026"

        line = Text()
        line.append(f"  {pr_id:>{id_width}}  ")
        if pr.get("isDraft"):
            line.append("(draft) ", style="yellow")
        if pr.get("autoCompleteSetBy"):
            line.append("(auto) ", style="green")
        line.append(f"{title} ")
        line.append(f"({branch})", style="blue")

        if not pr.get("isDraft"):
            has_conflicts = pr.get("mergeStatus") == "conflicts"
            reasons = []
            if has_conflicts:
                reasons.append("conflict")
            if blocked:
                reasons.append(str(blocked))

            if reasons:
                parts = []
                for r in reasons:
                    if r == "conflict":
                        parts.append("conflict")
                    else:
                        parts.append("votes")
                suffix = f"(blocked: {', '.join(parts)})"
                color = "red"
            elif novote:
                suffix = f"(waiting: {novote} votes)"
                color = "yellow"
            elif approved == len(required) and len(required) > 0:
                suffix = "(ready)"
                color = "green"
            else:
                suffix = None

            if suffix is not None:
                line.append(" ", style=color)
                line.append(suffix, style=color)

        console.print(line)

    return 0
