import os
import sys
import subprocess

from rich.console import Console

from .utils import (
    branch_exists_local,
    find_remote_branch,
    get_default_branch,
    get_ms_worktree,
    get_repo_name,
    get_worktree_parent_dir,
    has_uncommitted_changes,
    is_merge_in_progress,
    run,
)

console = Console(highlight=False)
console_stderr = Console(file=sys.stderr, highlight=False)


def cmd_mb(args):
    quiet = args.quiet
    continue_merge = args.cont
    abort = args.abort
    branch = args.branch

    if abort:
        return cmd_mb_abort(quiet)

    if continue_merge:
        if not branch:
            pending_branch, _ = find_pending_mb_worktree()
            if not pending_branch:
                print("Error: no pending merge found", file=sys.stderr)
                return 1
            branch = pending_branch
        return cmd_mb_continue(branch, quiet)

    if not branch:
        print("Error: branch name required", file=sys.stderr)
        return 1

    pending_branch, _ = find_pending_mb_worktree()
    if pending_branch:
        print(
            f"Error: pending merge for '{pending_branch}'",
            file=sys.stderr,
        )
        print("Run 'gg mb --continue' or 'gg mb --abort'", file=sys.stderr)
        return 1

    if has_uncommitted_changes():
        print(
            "Error: uncommitted changes detected. Commit or stash first.",
            file=sys.stderr,
        )
        return 1

    default_branch = get_default_branch()
    if not default_branch:
        print(
            "Error: could not determine default branch (main/master)", file=sys.stderr
        )
        return 1

    if not branch_exists_local(branch):
        remote_branch = find_remote_branch(branch)
        if not remote_branch:
            print(
                f"Error: branch '{branch}' does not exist locally or on origin",
                file=sys.stderr,
            )
            return 1
        if not quiet:
            print(
                f"Creating local branch '{branch}' tracking '{remote_branch}'...",
                file=sys.stderr,
            )
        result = run(["git", "branch", "--track", branch, remote_branch])
        if result.returncode != 0:
            print(
                f"Error creating local branch: {result.stderr.strip()}", file=sys.stderr
            )
            return 1

    worktree = get_ms_worktree()
    if worktree:
        if not quiet:
            print(f"Reusing worktree at {worktree['path']}...", file=sys.stderr)
        result = subprocess.run(
            ["git", "checkout", branch],
            cwd=worktree["path"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"Error checking out branch: {result.stderr.strip()}", file=sys.stderr
            )
            return 1
    else:
        parent_dir = get_worktree_parent_dir()
        repo_name = get_repo_name()
        worktree_path = os.path.join(parent_dir, f"{repo_name}_tmp_ms")
        os.makedirs(worktree_path, exist_ok=True)
        if not quiet:
            print(f"Creating worktree at {worktree_path}...", file=sys.stderr)
        result = run(["git", "worktree", "add", worktree_path, branch])
        if result.returncode != 0:
            print(f"Error creating worktree: {result.stderr.strip()}", file=sys.stderr)
            os.rmdir(worktree_path)
            return 1
        worktree = {"path": worktree_path}

    if not quiet:
        print(f"Merging origin/{default_branch} into {branch}...", file=sys.stderr)

    result = subprocess.run(
        ["git", "merge", f"origin/{default_branch}"],
        cwd=worktree["path"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console_stderr.print("[red]Merge conflict detected[/red]")
        print(f"Worktree left at: {worktree['path']}", file=sys.stderr)
        print("Resolve conflicts, then run: gg mb --continue", file=sys.stderr)
        return 1

    detach_worktree(worktree["path"])

    console.print(f"[green]Merged origin/{default_branch} into '{branch}'[/green]")
    return 0


def cmd_mb_continue(branch, quiet):
    worktree = get_ms_worktree()
    if not worktree:
        print("Error: no worktree found", file=sys.stderr)
        return 1

    worktree_path = worktree["path"]

    if not is_merge_in_progress(worktree_path):
        result = run(["git", "-C", worktree_path, "rev-parse", "--verify", "HEAD"])
        if result.returncode != 0:
            print("Error: worktree in unexpected state", file=sys.stderr)
            return 1

    result = subprocess.run(
        ["git", "commit", "--no-edit"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            pass
        else:
            print(f"Error committing merge: {result.stderr.strip()}", file=sys.stderr)
            return 1

    detach_worktree(worktree_path)

    default_branch = get_default_branch()
    console.print(f"[green]Merged origin/{default_branch} into '{branch}'[/green]")
    return 0


def cmd_mb_abort(quiet):
    pending_branch, worktree = find_pending_mb_worktree()
    if not worktree:
        print("Error: no pending merge found", file=sys.stderr)
        return 1

    worktree_path = worktree["path"]

    if not quiet:
        print("Aborting merge...", file=sys.stderr)

    subprocess.run(
        ["git", "merge", "--abort"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    detach_worktree(worktree_path)

    print("Aborted.", file=sys.stderr)
    return 0


def detach_worktree(worktree_path):
    subprocess.run(
        ["git", "checkout", "--detach", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )


def find_pending_mb_worktree():
    worktree = get_ms_worktree()
    if worktree and is_merge_in_progress(worktree["path"]):
        branch = worktree.get("branch", "")
        if branch.startswith("refs/heads/"):
            return branch.replace("refs/heads/", ""), worktree
    return None, None
