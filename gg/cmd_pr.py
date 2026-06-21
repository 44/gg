import json
import os
import shlex
import subprocess
import sys

from rich.console import Console
from rich.text import Text

from .utils import run

console = Console()


def cmd_pr(args):
    command = args.pr_command
    commands = {
        "list": cmd_pr_list,
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


def cmd_pr_list(args):
    creator = _get_git_email()
    if creator is None:
        return 1

    email_local = creator.split("@")[0] if "@" in creator else None

    paths = os.environ.get("PATH", "").split(os.pathsep)
    user_bin = os.path.expanduser("~/.local/bin")
    if user_bin not in paths:
        os.environ["PATH"] = f"{user_bin}{os.pathsep}{os.environ['PATH']}"

    cmd = f"az repos pr list --creator {shlex.quote(creator)} --status active --output json"
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        shell=True,
    )

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
        total = len(required)
        approved = sum(1 for r in required if r.get("vote", 0) >= 5)
        waiting = sum(1 for r in required if r.get("vote") == -5)

        if len(title) > TITLE_MAX:
            title = title[: TITLE_MAX - 1] + "\u2026"

        line = Text()
        line.append(f"  {pr_id:>{id_width}}  ")
        line.append(f"{approved}a", style="green" if approved else "grey15")
        line.append("/", style="grey15")
        line.append(f"{waiting}w", style="yellow" if waiting else "grey15")
        line.append("/", style="grey15")
        line.append(str(total), style="grey15" if total == 0 else "")
        line.append("  ")
        if pr.get("isDraft"):
            line.append("(draft) ", style="yellow")
        line.append(f"{title} ")
        line.append(f"({branch})", style="blue")
        if pr.get("autoCompleteSetBy"):
            line.append(" (ac)", style="green")
        console.print(line)

    return 0
