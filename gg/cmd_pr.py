import json
import os
import shlex
import subprocess
import sys

from .utils import run


def cmd_pr(args):
    command = args.pr_command
    commands = {
        "list": cmd_pr_list,
    }
    if command in commands:
        return commands[command](args)
    print(f"Unknown pr command: {command}", file=sys.stderr)
    return 1


def _get_git_user():
    result = run(["git", "config", "user.name"])
    if result.returncode != 0:
        print(
            "Failed to get git user name. Ensure git config user.name is set.",
            file=sys.stderr,
        )
        return None
    return result.stdout.strip()


def cmd_pr_list(args):
    creator = _get_git_user()
    if creator is None:
        return 1

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

    for pr in prs:
        pr_id = pr["pullRequestId"]
        draft = "[DRAFT]" if pr.get("isDraft", False) else "      "
        title = pr["title"]
        print(f"{pr_id:>6} {draft} {title}")

    return 0
