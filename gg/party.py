#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console(highlight=False)
console_stderr = Console(file=sys.stderr, highlight=False)


def run(cmd, capture=True, cwd=None):
    result = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd)
    return result


def get_repo_root():
    result = run(["git", "rev-parse", "--show-toplevel"])
    return result.stdout.strip() if result.returncode == 0 else None


def get_repo_name():
    repo_root = get_repo_root()
    if repo_root:
        return os.path.basename(repo_root)
    return "repo"


def get_worktree_parent_dir():
    repo_root = get_repo_root()
    if repo_root:
        return os.path.dirname(repo_root)
    return "/tmp"


def get_current_branch():
    result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else None


def branch_exists_local(branch):
    result = run(["git", "rev-parse", "--verify", f"refs/heads/{branch}"])
    return result.returncode == 0


def get_worktrees():
    result = run(["git", "worktree", "list", "--porcelain"])
    if result.returncode != 0:
        return []
    worktrees = []
    current = {}
    for line in result.stdout.strip().split("\n"):
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line.split(" ", 1)[1]}
        elif line.startswith("HEAD "):
            current["head"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            current["branch"] = line.split(" ", 1)[1]
    if current:
        worktrees.append(current)
    return worktrees


def get_party_worktree_path():
    parent_dir = get_worktree_parent_dir()
    repo_name = get_repo_name()
    return Path(parent_dir) / f".{repo_name}-party"


def get_party_worktree():
    worktree_path = get_party_worktree_path()
    for wt in get_worktrees():
        if Path(wt.get("path", "")) == worktree_path:
            return wt
    return None


def create_party_worktree(branch=None):
    existing = get_party_worktree()
    if existing:
        return existing

    run(["git", "worktree", "prune"])

    worktree_path = str(get_party_worktree_path())

    if branch:
        result = run(["git", "worktree", "add", worktree_path, branch])
    else:
        result = run(["git", "worktree", "add", "--detach", worktree_path, "HEAD"])

    if result.returncode != 0:
        print(f"git worktree add failed: {result.stderr}")
        return None

    return get_party_worktree()


def remove_party_worktree():
    wt = get_party_worktree()
    if wt:
        run(["git", "worktree", "remove", wt["path"], "--force"])
    run(["git", "worktree", "prune"])


def get_active_party():
    result = run(["git", "config", "--local", "party.active"])
    return result.stdout.strip() if result.returncode == 0 else None


def set_active_party(name):
    if name:
        return run(["git", "config", "--local", "party.active", name])
    else:
        return run(["git", "config", "--local", "--unset", "party.active"])


def get_party_config(name):
    result = run(["git", "config", "--local", f"party.{name}.default"])
    default = result.stdout.strip() if result.returncode == 0 else None

    result = run(["git", "config", "--local", f"party.{name}.branches"])
    branches_str = result.stdout.strip() if result.returncode == 0 else ""
    branches = [b.strip() for b in branches_str.split(",") if b.strip()]

    result = run(["git", "config", "--local", f"party.{name}.pending"])
    pending = result.stdout.strip() if result.returncode == 0 else None

    result = run(["git", "config", "--local", f"party.{name}.pendingTarget"])
    pending_target = result.stdout.strip() if result.returncode == 0 else None

    return {
        "default": default,
        "branches": branches,
        "pending": pending,
        "pendingTarget": pending_target,
    }


def save_party_config(
    name, default=None, branches=None, pending=None, pending_target=None
):
    if default is not None:
        run(["git", "config", "--local", f"party.{name}.default", default])
    if branches is not None:
        run(["git", "config", "--local", f"party.{name}.branches", ",".join(branches)])
    if pending is not None:
        run(["git", "config", "--local", f"party.{name}.pending", pending])
    if pending_target is not None:
        run(["git", "config", "--local", f"party.{name}.pendingTarget", pending_target])


def delete_party_config(name):
    run(["git", "config", "--local", "--unset", f"party.{name}.default"])
    run(["git", "config", "--local", "--unset", f"party.{name}.branches"])
    run(["git", "config", "--local", "--unset", f"party.{name}.pending"])
    run(["git", "config", "--local", "--unset", f"party.{name}.pendingTarget"])


def clear_pending_state(name):
    run(["git", "config", "--local", "--unset", f"party.{name}.pending"])
    run(["git", "config", "--local", "--unset", f"party.{name}.pendingTarget"])


def has_staged_or_unstaged():
    result = run(["git", "status", "--porcelain"])
    if result.returncode != 0:
        return True
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        status = line[:2]
        if status[0] in "MADRC" or status[1] in "MD":
            return True
    return False


def get_party_branch_name(name):
    return f"party/{name}"


def is_merge_in_progress(worktree_path):
    merge_head = os.path.join(worktree_path, ".git", "MERGE_HEAD")
    return os.path.exists(merge_head)


def is_cherry_pick_in_progress(worktree_path):
    cherry_head = os.path.join(worktree_path, ".git", "CHERRY_PICK_HEAD")
    return os.path.exists(cherry_head)


def get_branch_commits(branch, exclude_branches=None):
    if exclude_branches is None:
        exclude_branches = []

    args = ["git", "log", "--no-merges", "--format=%H %s", branch]
    for eb in exclude_branches:
        args.append(f"^{eb}")

    result = run(args)
    if result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(" ", 1)
        commits.append(
            {"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""}
        )
    return commits


def detect_unique_commits(merged_branch, party_branches):
    return get_branch_commits(merged_branch, party_branches)


def build_merged_view_in_worktree(branches):
    if not branches:
        return None

    worktree = get_party_worktree()
    if not worktree:
        return None

    worktree_path = worktree["path"]

    subprocess.run(
        ["git", "checkout", "--detach", branches[0]],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    for branch in branches[1:]:
        result = subprocess.run(
            ["git", "merge", branch, "--no-edit"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    return result.stdout.strip()


def rebuild_merged_view(name, branches):
    party_branch = get_party_branch_name(name)

    current = get_current_branch()
    if current == party_branch:
        run(["git", "checkout", "--detach", "HEAD"])

    worktree = get_party_worktree()
    if not worktree:
        worktree = create_party_worktree()
        if not worktree:
            return False

    commit_hash = build_merged_view_in_worktree(branches)
    if not commit_hash:
        return False

    run(["git", "branch", "-f", party_branch, commit_hash])
    return True


def checkout_party_branch(name):
    party_branch = get_party_branch_name(name)
    result = run(["git", "checkout", party_branch])
    return result.returncode == 0


def delete_party_branch(name):
    party_branch = get_party_branch_name(name)
    result = run(["git", "branch", "-D", party_branch])
    return result.returncode == 0


def cmd_party_start(args):
    name = args.name
    branches = args.branches or []
    quiet = args.quiet

    active = get_active_party()
    if active:
        console_stderr.print(
            f"[red]Error: active party '{active}' exists. Finish it first.[/red]"
        )
        return 1

    if has_staged_or_unstaged():
        console_stderr.print(
            "[red]Error: staged or unstaged changes detected. Commit or stash first.[/red]"
        )
        return 1

    current = get_current_branch()
    if not current:
        console_stderr.print("[red]Error: could not determine current branch.[/red]")
        return 1

    all_branches = [current] + [b for b in branches if b != current]

    for branch in all_branches:
        if not branch_exists_local(branch):
            console_stderr.print(
                f"[red]Error: branch '{branch}' does not exist locally.[/red]"
            )
            return 1

    party_branch = get_party_branch_name(name)
    if branch_exists_local(party_branch):
        console_stderr.print(
            f"[red]Error: branch '{party_branch}' already exists.[/red]"
        )
        return 1

    if not quiet:
        console_stderr.print(
            f"Creating party '{name}' with branches: {', '.join(all_branches)}"
        )

    save_party_config(name, default=current, branches=all_branches)
    set_active_party(name)

    worktree = create_party_worktree()
    if not worktree:
        console_stderr.print("[red]Error: could not create worktree.[/red]")
        set_active_party(None)
        delete_party_config(name)
        return 1

    commit_hash = build_merged_view_in_worktree(all_branches)
    if not commit_hash:
        console_stderr.print(
            "[red]Error: failed to build merged view. Check for merge conflicts.[/red]"
        )
        set_active_party(None)
        delete_party_config(name)
        return 1

    run(["git", "branch", party_branch, commit_hash])

    if not checkout_party_branch(name):
        console_stderr.print("[red]Error: failed to checkout party branch.[/red]")
        set_active_party(None)
        delete_party_config(name)
        return 1

    console.print(f"[green]Started party '{name}' on branch '{party_branch}'[/green]")
    return 0


def cmd_party_add(args):
    branch = args.branch
    quiet = args.quiet

    active = get_active_party()
    if not active:
        console_stderr.print("[red]Error: no active party. Start one first.[/red]")
        return 1

    if not branch_exists_local(branch):
        console_stderr.print(
            f"[red]Error: branch '{branch}' does not exist locally.[/red]"
        )
        return 1

    config = get_party_config(active)
    if branch in config["branches"]:
        console_stderr.print(f"[yellow]Branch '{branch}' already in party.[/yellow]")
        return 0

    new_branches = config["branches"] + [branch]
    save_party_config(active, branches=new_branches)

    if not quiet:
        console_stderr.print(f"Added '{branch}' to party '{active}'")

    sync_args = type("Args", (), {"quiet": quiet})()
    return cmd_party_sync(sync_args)


def cmd_party_default(args):
    branch = args.branch
    quiet = args.quiet

    active = get_active_party()
    if not active:
        console_stderr.print("[red]Error: no active party. Start one first.[/red]")
        return 1

    if not branch_exists_local(branch):
        console_stderr.print(
            f"[red]Error: branch '{branch}' does not exist locally.[/red]"
        )
        return 1

    config = get_party_config(active)
    if branch not in config["branches"]:
        console_stderr.print(
            f"[red]Error: branch '{branch}' is not in the party. Add it first.[/red]"
        )
        return 1

    save_party_config(active, default=branch)

    if not quiet:
        console.print(f"[green]Set '{branch}' as default for party '{active}'[/green]")
    return 0


def cmd_party_move(args):
    commit = args.commit
    target_branch = args.branch
    quiet = args.quiet

    active = get_active_party()
    if not active:
        console_stderr.print("[red]Error: no active party. Start one first.[/red]")
        return 1

    if has_staged_or_unstaged():
        console_stderr.print(
            "[red]Error: staged or unstaged changes detected. Commit or stash first.[/red]"
        )
        return 1

    config = get_party_config(active)
    if target_branch not in config["branches"]:
        console_stderr.print(
            f"[red]Error: branch '{target_branch}' is not in the party.[/red]"
        )
        return 1

    worktree = get_party_worktree()
    if not worktree:
        console_stderr.print("[red]Error: party worktree not found.[/red]")
        return 1

    worktree_path = worktree["path"]

    save_party_config(active, pending="move", pending_target=target_branch)

    result = subprocess.run(
        ["git", "checkout", target_branch],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console_stderr.print(
            f"[red]Error checking out {target_branch} in worktree[/red]"
        )
        clear_pending_state(active)
        return 1

    result = subprocess.run(
        ["git", "cherry-pick", commit],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console_stderr.print("[red]Cherry-pick conflict detected[/red]")
        console_stderr.print(f"Worktree at: {worktree_path}")
        console_stderr.print("Resolve conflicts, then run: gg party continue")
        return 1

    clear_pending_state(active)

    if not quiet:
        console_stderr.print("Rebuilding merged view...")

    if not rebuild_merged_view(active, config["branches"]):
        console_stderr.print("[red]Error: failed to rebuild merged view.[/red]")
        return 1

    if not checkout_party_branch(active):
        console_stderr.print("[red]Error: failed to checkout party branch.[/red]")
        return 1

    console.print(f"[green]Moved commit to '{target_branch}'[/green]")
    return 0


def cmd_party_sync(args):
    quiet = args.quiet

    active = get_active_party()
    if not active:
        console_stderr.print("[red]Error: no active party. Start one first.[/red]")
        return 1

    if has_staged_or_unstaged():
        console_stderr.print(
            "[red]Error: staged or unstaged changes detected. Commit or stash first.[/red]"
        )
        return 1

    config = get_party_config(active)
    party_branch = get_party_branch_name(active)

    unique_commits = detect_unique_commits(party_branch, config["branches"])

    default_branch = config["default"]
    if not default_branch:
        console_stderr.print("[red]Error: no default branch set for party.[/red]")
        return 1

    worktree = get_party_worktree()
    if not worktree:
        console_stderr.print("[red]Error: party worktree not found.[/red]")
        return 1

    worktree_path = worktree["path"]

    if unique_commits:
        if not quiet:
            console_stderr.print(
                f"Moving {len(unique_commits)} commit(s) to '{default_branch}'..."
            )

        result = subprocess.run(
            ["git", "checkout", default_branch],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )

        for commit in unique_commits:
            result = subprocess.run(
                ["git", "cherry-pick", commit["hash"]],
                cwd=worktree_path,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                console_stderr.print(
                    f"[red]Error cherry-picking {commit['hash'][:8]}[/red]"
                )
                save_party_config(active, pending="sync")
                return 1

    if not quiet:
        console_stderr.print("Rebuilding merged view...")

    if not rebuild_merged_view(active, config["branches"]):
        console_stderr.print("[red]Error: failed to rebuild merged view.[/red]")
        return 1

    if not checkout_party_branch(active):
        console_stderr.print("[red]Error: failed to checkout party branch.[/red]")
        return 1

    console.print(f"[green]Synced party '{active}'[/green]")
    return 0


def cmd_party_status(args):
    active = get_active_party()

    if not active:
        console.print("[yellow]No active party[/yellow]")
        return 0

    config = get_party_config(active)
    party_branch = get_party_branch_name(active)

    console.print(f"[bold]Active party: {active}[/bold]")
    console.print(f"Default branch: [green]{config['default']}[/green]")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Branch")
    table.add_column("Commits")

    for branch in config["branches"]:
        commits = get_branch_commits(branch, [branch + "~"])[::-1]
        is_default = " (default)" if branch == config["default"] else ""
        table.add_row(f"{branch}{is_default}", str(len(commits)))

    console.print(table)

    unique = detect_unique_commits(party_branch, config["branches"])
    if unique:
        console.print()
        console.print(f"[yellow]Unassigned commits on {party_branch}:[/yellow]")
        for commit in unique[:10]:
            console.print(f"  {commit['hash'][:8]} {commit['message'][:50]}")
        if len(unique) > 10:
            console.print(f"  ... and {len(unique) - 10} more")

    return 0


def cmd_party_finish(args):
    quiet = args.quiet

    active = get_active_party()
    if not active:
        console_stderr.print("[red]Error: no active party to finish.[/red]")
        return 1

    if has_staged_or_unstaged():
        console_stderr.print(
            "[red]Error: staged or unstaged changes detected. Commit or stash first.[/red]"
        )
        return 1

    config = get_party_config(active)
    default_branch = config["default"]

    sync_args = type("Args", (), {"quiet": quiet})()
    result = cmd_party_sync(sync_args)
    if result != 0:
        return result

    if not quiet:
        console_stderr.print(f"Checking out default branch '{default_branch}'...")

    result = run(["git", "checkout", default_branch])
    if result.returncode != 0:
        console_stderr.print(f"[red]Error: failed to checkout '{default_branch}'[/red]")
        return 1

    delete_party_branch(active)
    delete_party_config(active)
    set_active_party(None)

    console.print(f"[green]Finished party '{active}'[/green]")
    return 0


def cmd_party_continue(args):
    quiet = args.quiet

    active = get_active_party()
    if not active:
        console_stderr.print("[red]Error: no active party.[/red]")
        return 1

    config = get_party_config(active)
    pending = config.get("pending")

    if not pending:
        console_stderr.print("[yellow]No pending operation to continue.[/yellow]")
        return 0

    worktree = get_party_worktree()
    if not worktree:
        console_stderr.print("[red]Error: party worktree not found.[/red]")
        return 1

    worktree_path = worktree["path"]

    if pending == "move":
        target_branch = config.get("pendingTarget")
        if not target_branch:
            console_stderr.print("[red]Error: no target branch for pending move.[/red]")
            return 1

        result = subprocess.run(
            ["git", "cherry-pick", "--continue"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            console_stderr.print(f"[red]Error: {result.stderr.strip()}[/red]")
            return 1

        clear_pending_state(active)

        sync_args = type("Args", (), {"quiet": quiet})()
        return cmd_party_sync(sync_args)

    elif pending == "sync":
        result = subprocess.run(
            ["git", "cherry-pick", "--continue"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            console_stderr.print(f"[red]Error: {result.stderr.strip()}[/red]")
            return 1

        clear_pending_state(active)

        if not rebuild_merged_view(active, config["branches"]):
            console_stderr.print("[red]Error: failed to rebuild merged view.[/red]")
            return 1

        if not checkout_party_branch(active):
            console_stderr.print("[red]Error: failed to checkout party branch.[/red]")
            return 1

        console.print(f"[green]Continued party '{active}'[/green]")
        return 0

    return 1


def cmd_party_abort(args):
    active = get_active_party()
    if not active:
        console_stderr.print("[red]Error: no active party.[/red]")
        return 1

    config = get_party_config(active)
    pending = config.get("pending")

    if not pending:
        console_stderr.print("[yellow]No pending operation to abort.[/yellow]")
        return 0

    worktree = get_party_worktree()
    if not worktree:
        console_stderr.print("[red]Error: party worktree not found.[/red]")
        return 1

    worktree_path = worktree["path"]

    subprocess.run(
        ["git", "cherry-pick", "--abort"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        ["git", "merge", "--abort"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    clear_pending_state(active)

    console.print(f"[green]Aborted pending operation for party '{active}'[/green]")
    return 0


def cmd_party(args):
    command = args.party_command

    commands = {
        "start": cmd_party_start,
        "add": cmd_party_add,
        "default": cmd_party_default,
        "move": cmd_party_move,
        "sync": cmd_party_sync,
        "status": cmd_party_status,
        "finish": cmd_party_finish,
        "continue": cmd_party_continue,
        "abort": cmd_party_abort,
    }

    if command in commands:
        return commands[command](args)
    else:
        console_stderr.print(f"[red]Unknown party command: {command}[/red]")
        return 1
