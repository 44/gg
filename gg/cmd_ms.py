import os
import sys
import subprocess

from rich.console import Console

from .utils import (
    branch_exists_local,
    find_remote_branch,
    get_current_branch,
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


def cmd_ms(args):
    quiet = args.quiet
    continue_merge = args.cont
    abort = args.abort
    branch = args.branch

    if abort:
        return cmd_ms_abort(quiet)

    if continue_merge:
        if not branch:
            from .utils import find_pending_ms_worktree

            branch, worktree = find_pending_ms_worktree()
            if not branch:
                print("Error: no pending merge found", file=sys.stderr)
                return 1
        return cmd_ms_continue(branch, quiet)

    if not branch:
        print("Error: branch name required", file=sys.stderr)
        return 1

    from .utils import find_pending_ms_worktree

    pending_branch, pending_wt = find_pending_ms_worktree()
    if pending_wt:
        print(
            f"Error: pending merge for '{pending_branch}' at {pending_wt['path']}",
            file=sys.stderr,
        )
        print("Run 'gg ms --continue' or 'gg ms --abort'", file=sys.stderr)
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

    current = get_current_branch()
    if current == branch:
        print(f"Error: already on branch '{branch}'", file=sys.stderr)
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

    parent_dir = get_worktree_parent_dir()
    repo_name = get_repo_name()
    worktree_path = os.path.join(parent_dir, f"{repo_name}_tmp_ms")

    existing_wt = get_ms_worktree()
    if existing_wt:
        if not quiet:
            print(f"Reusing worktree at {worktree_path}...", file=sys.stderr)
        result = subprocess.run(
            ["git", "checkout", branch],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"Error checking out branch: {result.stderr.strip()}", file=sys.stderr
            )
            return 1
    else:
        os.makedirs(worktree_path, exist_ok=True)
        if not quiet:
            print(f"Creating worktree at {worktree_path}...", file=sys.stderr)
        result = run(["git", "worktree", "add", worktree_path, branch])
        if result.returncode != 0:
            print(f"Error creating worktree: {result.stderr.strip()}", file=sys.stderr)
            os.rmdir(worktree_path)
            return 1

    if not quiet:
        print(f"Merging {default_branch} into {branch}...", file=sys.stderr)

    result = subprocess.run(
        ["git", "merge", default_branch],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console_stderr.print("[red]Merge conflict detected[/red]")
        print(f"Worktree left at: {worktree_path}", file=sys.stderr)
        print("Resolve conflicts, then run: gg ms --continue", file=sys.stderr)
        return 1

    result = subprocess.run(
        ["git", "checkout", "--detach", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    result = run(["git", "checkout", branch])
    if result.returncode != 0:
        print(f"Error switching to branch: {result.stderr.strip()}", file=sys.stderr)
        return 1

    console.print(f"[green]Switched to refreshed branch '{branch}'[/green]")
    return 0


def cmd_ms_continue(branch, quiet):
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

    if not quiet:
        print("Detaching worktree...", file=sys.stderr)

    subprocess.run(
        ["git", "checkout", "--detach", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    result = run(["git", "checkout", branch])
    if result.returncode != 0:
        print(f"Error switching to branch: {result.stderr.strip()}", file=sys.stderr)
        return 1

    console.print(f"[green]Switched to refreshed branch '{branch}'[/green]")
    return 0


def cmd_ms_abort(quiet):
    worktree = get_ms_worktree()
    if not worktree:
        print("Error: no worktree found", file=sys.stderr)
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

    if not quiet:
        print("Detaching worktree...", file=sys.stderr)

    subprocess.run(
        ["git", "checkout", "--detach", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    print("Aborted.", file=sys.stderr)
    return 0
