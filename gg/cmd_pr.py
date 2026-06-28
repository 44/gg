import json
import os
import shlex
import subprocess
import sys
import tempfile

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


def _run_az(cmd):
    _ensure_path()
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", shell=True)


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
                    threads = thread_data.get("value", thread_data if isinstance(thread_data, list) else [])
                    thread_total = len(threads)
                    thread_active = sum(1 for t in threads if t.get("status") == "active")
                except json.JSONDecodeError:
                    pass

            policy_approved = 0
            policy_running = 0
            policy_total = 0
            policy_result = _run_az(f"az repos pr policy list --id {pr_id} --output json")
            if policy_result.returncode == 0:
                with open(os.path.join(pr_cache_dir, "policies.json"), "w") as f:
                    f.write(policy_result.stdout)
                try:
                    policies = json.loads(policy_result.stdout)
                    if isinstance(policies, list):
                        policy_running = sum(1 for p in policies if p.get("status") in ("running", "queued"))
                        policy_approved = sum(1 for p in policies if p.get("status") == "approved")
                        policy_total = len(policies)
                except json.JSONDecodeError:
                    pass

            print(f"PR {pr_id}: {thread_active}/{thread_total} threads, {policy_approved}/{policy_running}/{policy_total} policies", file=sys.stderr)
        else:
            if os.path.isdir(pr_cache_dir):
                import shutil
                shutil.rmtree(pr_cache_dir)
                print(f"PR {pr_id}: cleaned up", file=sys.stderr)

    return 0


def cmd_pr_show(args):
    pr_id = args.pr_id
    cache_dir = os.path.join(os.path.expanduser("~"), ".local", "cache", "gg", f"pr-{pr_id}")

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

    VOTE_LABELS = {10: "approved", 5: "approved w/suggestions", 0: "no vote", -5: "waiting for author", -10: "rejected"}

    description = pr.get("description") or ""

    console.print(f"[bold]PR {pr_id}:[/bold] {title}")
    console.print(f"  [dim]Branch:[/dim]  {branch}")
    console.print(f"  [dim]Creator:[/dim] {creator}")
    if description:
        console.print(f"  [dim]Description:[/dim]")
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
            result = _run_az(f"az rest --url {shlex.quote(thread_url)} --resource {RESOURCE} --output json")
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    threads = data.get("value", data if isinstance(data, list) else [])
                except json.JSONDecodeError:
                    pass

    active_threads = [t for t in threads if t.get("status") == "active"]
    if active_threads:
        console.print(f"  [bold]Active threads:[/bold]")
        for t in active_threads:
            tid = t.get("id", "")
            comments = t.get("comments") or []
            first = comments[0] if comments else {}
            author = first.get("author", {}).get("uniqueName", "")
            content = first.get("content", "")
            first_line = next((l.strip() for l in content.split("\n") if l.strip() and not l.strip().startswith("[comment]:")), "")[:80] if content else ""
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

    POLICY_COLORS = {"approved": "green", "rejected": "red", "running": "yellow", "queued": "yellow", "broken": "red", "notApplicable": "grey62"}

    if isinstance(policies, list) and policies:
        required = [p for p in policies if p.get("configuration", {}).get("isBlocking")]
        if required:
            console.print(f"  [bold]Required policies:[/bold]")
            for p in required:
                pid = p.get("configuration", {}).get("id", "")
                cfg = p.get("configuration", {})
                settings = cfg.get("settings", {})
                name = (settings.get("displayName")
                        or settings.get("defaultDisplayName")
                        or settings.get("statusName")
                        or cfg.get("displayName")
                        or cfg.get("type", {}).get("displayName", ""))
                status = p.get("status", "")
                color = POLICY_COLORS.get(status, "")
                line = Text(f"    #{pid} {name}  ")
                line.append(status, style=color)
                console.print(line)

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
