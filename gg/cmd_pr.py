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
    return subprocess.run(cmd, capture_output=True, text=True, shell=True)


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

    update_cmd = f"az repos pr update --id {pr_id}"
    if changed:
        update_cmd += f" --title {shlex.quote(new_title)}"
        if new_description:
            desc_lines = " ".join(shlex.quote(line) for line in new_description.split("\n"))
            update_cmd += f" --description {desc_lines}"
    if is_draft:
        update_cmd += " --draft false"

    if not changed and not is_draft:
        print("No changes and PR is already published.", file=sys.stderr)
        return 0

    result = _run_az(update_cmd)
    if result.returncode != 0:
        print(f"Failed to update PR: {result.stderr}", file=sys.stderr)
        return 1

    print(f"PR {pr_id} updated.", file=sys.stderr)
    return 0


def cmd_pr_list(args):
    creator = _get_git_email()
    if creator is None:
        return 1

    email_local = creator.split("@")[0] if "@" in creator else None

    cmd = f"az repos pr list --creator {shlex.quote(creator)} --status active --output json"
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
        line.append(f"{title} ")
        line.append(f"({branch})", style="blue")

        if not pr.get("isDraft"):
            if blocked:
                suffix = f"(blocked: {blocked}"
                color = "red"
            elif novote:
                suffix = f"(waiting: {novote}"
                color = "yellow"
            elif approved == len(required) and len(required) > 0:
                suffix = "(ready"
                color = "green"
            else:
                suffix = None

            if suffix is not None:
                if pr.get("autoCompleteSetBy"):
                    suffix += ", ac"
                suffix += ")"
                line.append(" ", style=color)
                line.append(suffix, style=color)
        elif pr.get("autoCompleteSetBy"):
            line.append(" (ac)", style="green")

        console.print(line)

    return 0
