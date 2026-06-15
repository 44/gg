import os
import subprocess
import tempfile

from rich.console import Console

console = Console(highlight=False)


def run(cmd, capture=True):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    return result


def get_local_branches():
    result = run(["git", "branch", "--format=%(refname:short) %(upstream:short)"])
    if result.returncode != 0:
        return []

    branches = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        branch = parts[0]
        upstream = parts[1].strip() if len(parts) > 1 else None
        if upstream:
            branches.append((branch, upstream))
    return branches


def can_fast_forward(branch, upstream):
    result = run(["git", "merge-base", "--is-ancestor", branch, upstream])
    return result.returncode == 0


def get_ahead_behind(branch, upstream):
    result = run(
        ["git", "rev-list", "--left-right", "--count", f"{branch}...{upstream}"]
    )
    if result.returncode == 0:
        ahead, behind = result.stdout.strip().split()
        return int(ahead), int(behind)
    return 0, 0


def format_status(ahead, behind):
    parts = [f"ahead:[green]{ahead}[/green]"]
    if behind > 0:
        parts.append(f"behind:[red]{behind}[/red]")
    return " ".join(parts)


def fast_forward(branch, upstream):
    if branch == get_current_branch():
        return run(["git", "merge", "--ff-only", upstream])
    else:
        return run(["git", "fetch", ".", upstream + ":" + branch])


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
    return tempfile.gettempdir()


def get_current_branch():
    result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else None


def branch_exists_local(branch):
    result = run(["git", "rev-parse", "--verify", f"refs/heads/{branch}"])
    return result.returncode == 0


def find_remote_branch(branch):
    result = run(["git", "rev-parse", "--verify", f"refs/remotes/origin/{branch}"])
    if result.returncode == 0:
        return f"origin/{branch}"
    return None


def has_uncommitted_changes():
    result = run(["git", "status", "--porcelain"])
    if result.returncode != 0:
        return True
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        status = line[:2]
        if status.strip() and not status.startswith("?"):
            return True
    return False


def get_default_branch():
    result = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
    if result.returncode == 0:
        ref = result.stdout.strip()
        return ref.replace("refs/remotes/origin/", "")
    for branch in ["main", "master"]:
        result = run(["git", "rev-parse", "--verify", f"refs/heads/{branch}"])
        if result.returncode == 0:
            return branch
    return None


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


def get_ms_worktree():
    parent_dir = get_worktree_parent_dir()
    repo_name = get_repo_name()
    worktree_path = os.path.join(parent_dir, f"{repo_name}_tmp_ms")
    for wt in get_worktrees():
        if wt.get("path") == worktree_path:
            return wt
    return None


def find_pending_ms_worktree():
    wt = get_ms_worktree()
    if wt and is_merge_in_progress(wt["path"]):
        branch = wt.get("branch", "")
        if branch.startswith("refs/heads/"):
            return branch.replace("refs/heads/", ""), wt
    return None, None


def is_merge_in_progress(worktree_path):
    merge_head = os.path.join(worktree_path, ".git", "MERGE_HEAD")
    if os.path.exists(merge_head):
        return True
    return False


def get_rb_worktree():
    parent_dir = get_worktree_parent_dir()
    repo_name = get_repo_name()
    worktree_path = os.path.join(parent_dir, f"{repo_name}_tmp_rb")
    for wt in get_worktrees():
        if wt.get("path") == worktree_path:
            return wt
    return None


def find_pending_rb_worktree():
    wt = get_rb_worktree()
    if wt and is_rebase_in_progress(wt["path"]):
        branch = wt.get("branch", "")
        if branch.startswith("refs/heads/"):
            return branch.replace("refs/heads/", ""), wt
    return None, None


def is_rebase_in_progress(worktree_path):
    rebase_apply = os.path.join(worktree_path, ".git", "rebase-apply")
    rebase_merge = os.path.join(worktree_path, ".git", "rebase-merge")
    if os.path.exists(rebase_apply) or os.path.exists(rebase_merge):
        return True
    return False
