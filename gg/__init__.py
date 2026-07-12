#!/usr/bin/env python3

__version__ = "0.1.0"

import argparse
import sys

from .party import cmd_party

from .cmd_install import cmd_install
from .cmd_cleanup import cmd_cleanup
from .cmd_fff import cmd_fff
from .cmd_mb import cmd_mb
from .cmd_ms import cmd_ms
from .cmd_pff import cmd_pff
from .cmd_rb import cmd_rb
from .cmd_wc import cmd_wc
from .cmd_pr import cmd_pr


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress progress messages"
    )

    parser = argparse.ArgumentParser(
        description="gg - git productivity tools for fast-forward workflows and multi-branch merging.",
        parents=[common],
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fff_parser = subparsers.add_parser(
        "fff",
        help="Fetch all branches and fast-forward local branches",
        description="Fetches all configured remotes with pruning, then fast-forwards each local branch "
        "whose upstream can be applied without divergence. Branches with unpushed local commits "
        "or that have diverged from upstream are skipped.",
        parents=[common],
    )
    fff_parser.set_defaults(func=cmd_fff)

    pff_parser = subparsers.add_parser(
        "pff",
        help="Push local branches that can be fast-forwarded on remote",
        description="Pushes all local branches that are strictly ahead of their upstream (no new "
        "commits on the remote side). Branches with diverged history are skipped to avoid "
        "force-pushing.",
        parents=[common],
    )
    pff_parser.set_defaults(func=cmd_pff)

    install_parser = subparsers.add_parser(
        "install",
        help="Install gg as a uv tool and create command wrappers",
        description="Installs gg via 'uv tool install' from GitHub, then creates executable "
        "wrapper scripts for gg commands (fff, mb, ms, party, pff, wc, rb, cleanup) in "
        "~/.local/bin (Linux) or %%USERPROFILE%%\\bin (Windows). "
        "Wrappers call 'gg <cmd>' directly. Overwrites existing scripts.",
        parents=[common],
    )
    install_parser.set_defaults(func=cmd_install)

    ms_parser = subparsers.add_parser(
        "ms",
        help="Merge default branch into branch and switch to it",
        description="Creates a temporary git worktree, checks out the specified branch, merges the "
        "local default branch (main/master) into it, then switches the main working directory "
        "to the refreshed branch. Useful for updating a feature branch without losing your "
        "current working state.",
        parents=[common],
    )
    ms_parser.add_argument("branch", nargs="?", help="branch to merge and switch to")
    ms_parser.add_argument(
        "-c",
        "--continue",
        dest="cont",
        action="store_true",
        help="continue after resolving conflicts",
    )
    ms_parser.add_argument(
        "--abort",
        action="store_true",
        help="abort pending merge and detach worktree",
    )
    ms_parser.set_defaults(func=cmd_ms)

    mb_parser = subparsers.add_parser(
        "mb",
        help="Merge origin/default branch into branch via worktree",
        description="Creates a temporary git worktree, checks out the specified branch, and merges "
        "origin/<default-branch> into it. Unlike ms, this merges the remote tracking branch "
        "rather than the local default branch, ensuring the latest remote changes are pulled in.",
        parents=[common],
    )
    mb_parser.add_argument("branch", nargs="?", help="branch to merge into")
    mb_parser.add_argument(
        "-c",
        "--continue",
        dest="cont",
        action="store_true",
        help="continue after resolving conflicts",
    )
    mb_parser.add_argument(
        "--abort",
        action="store_true",
        help="abort pending merge and detach worktree",
    )
    mb_parser.set_defaults(func=cmd_mb)

    rb_parser = subparsers.add_parser(
        "rb",
        help="Rebase branch onto default branch via worktree",
        description="Creates a temporary git worktree, checks out the specified branch, rebases it "
        "onto the local default branch (main/master), then switches the main working directory "
        "to the rebased branch. Conflicts are reported and the worktree is left in place for "
        "resolution.",
        parents=[common],
    )
    rb_parser.add_argument("branch", nargs="?", help="branch to rebase")
    rb_parser.add_argument(
        "-c",
        "--continue",
        dest="cont",
        action="store_true",
        help="continue after resolving conflicts",
    )
    rb_parser.add_argument(
        "--abort",
        action="store_true",
        help="abort pending rebase and detach worktree",
    )
    rb_parser.set_defaults(func=cmd_rb)

    party_parser = subparsers.add_parser(
        "party",
        help="Multi-branch merging workflow (party mode)",
        description="Party mode enables working on multiple branches simultaneously. It creates a "
        "merged view of all party branches in a worktree, allowing you to see and manage the "
        "combined state. Use sub-commands to start, add branches, move commits, sync, and "
        "finish the party.",
        parents=[common],
    )
    party_sub = party_parser.add_subparsers(dest="party_command", required=True)

    party_start = party_sub.add_parser(
        "start",
        help="Start a new party with the current branch and optional additional branches",
        parents=[common],
    )
    party_start.add_argument("name", help="name for the party")
    party_start.add_argument(
        "branches", nargs="*", help="additional branches to include"
    )
    party_start.set_defaults(func=cmd_party)

    party_add = party_sub.add_parser(
        "add",
        help="Add a branch to the active party and rebuild merged view",
        parents=[common],
    )
    party_add.add_argument("branch", help="branch to add")
    party_add.set_defaults(func=cmd_party)

    party_default = party_sub.add_parser(
        "default",
        help="Set the default branch for the party (target for sync)",
        parents=[common],
    )
    party_default.add_argument("branch", help="branch to set as default")
    party_default.set_defaults(func=cmd_party)

    party_move = party_sub.add_parser(
        "move",
        help="Cherry-pick a commit from merged view to a specific party branch",
        parents=[common],
    )
    party_move.add_argument("commit", help="commit hash to move")
    party_move.add_argument("branch", help="target branch")
    party_move.set_defaults(func=cmd_party)

    party_sync = party_sub.add_parser(
        "sync",
        help="Cherry-pick unassigned commits to default branch and rebuild merged view",
        parents=[common],
    )
    party_sync.set_defaults(func=cmd_party)

    party_status = party_sub.add_parser(
        "status",
        help="Display active party configuration, branches, and unassigned commits",
        parents=[common],
    )
    party_status.set_defaults(func=cmd_party)

    party_finish = party_sub.add_parser(
        "finish",
        help="Sync changes, checkout default branch, and clean up party resources",
        parents=[common],
    )
    party_finish.set_defaults(func=cmd_party)

    party_continue = party_sub.add_parser(
        "continue",
        help="Continue a pending cherry-pick or sync after resolving conflicts",
        parents=[common],
    )
    party_continue.set_defaults(func=cmd_party)

    party_abort = party_sub.add_parser(
        "abort",
        help="Abort the current cherry-pick or merge operation and clear pending state",
        parents=[common],
    )
    party_abort.set_defaults(func=cmd_party)

    wc_parser = subparsers.add_parser(
        "wc",
        help="Show combined diff stats with file status and line counts",
        description="Displays a combined view of git diff --name-status and --numstat, showing "
        "the status (Added, Modified, Deleted, Renamed) of each file along with "
        "added/deleted line counts. Defaults to diff against origin/<default-branch>.",
        parents=[common],
    )
    wc_parser.add_argument(
        "diff_spec", nargs="?", help="diff specification (e.g., origin/main...HEAD)"
    )
    wc_parser.set_defaults(func=cmd_wc)

    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Delete local branches that have been merged into the default branch",
        description="Identifies local branches without upstream tracking that have been fully "
        "merged into the default branch and deletes them. The current branch, default branch, "
        "and branches with unpushed commits are preserved. Supports dry-run and force-delete modes.",
        parents=[common],
    )
    cleanup_parser.add_argument(
        "-n", "--dry-run", action="store_true", help="show what would be deleted"
    )
    cleanup_parser.add_argument(
        "-f", "--force", action="store_true", help="force delete branches"
    )
    cleanup_parser.set_defaults(func=cmd_cleanup)

    pr_parser = subparsers.add_parser(
        "pr",
        help="Manage Azure DevOps pull requests",
        description="Manage Azure DevOps pull requests. Requires 'az' CLI to be installed and configured.",
        parents=[common],
    )
    pr_sub = pr_parser.add_subparsers(dest="pr_command", required=True)

    pr_list = pr_sub.add_parser(
        "list",
        help="List active pull requests",
        description="Lists active Azure DevOps pull requests. By default filtered by the current "
        "git user as creator. Use --review to show PRs awaiting your review, or --all for all active PRs.",
        parents=[common],
    )
    pr_list.add_argument(
        "--review", action="store_true", help="Show PRs where you are a reviewer"
    )
    pr_list.add_argument(
        "--all", action="store_true", dest="all_prs", help="Show all active PRs"
    )
    pr_list.set_defaults(func=cmd_pr)

    pr_publish = pr_sub.add_parser(
        "publish",
        help="Publish a pull request",
        description="Fetches PR info, syncs local branch, opens editor to update title/description, "
        "and publishes the PR if it was in draft state. If a file path is provided, reads title "
        "and description from the file instead of opening an editor.",
        parents=[common],
    )
    pr_publish.add_argument("pr_id", type=int, help="Pull request ID")
    pr_publish.add_argument(
        "file",
        nargs="?",
        help="Path to file with title (first line) and description (rest)",
    )
    pr_publish.set_defaults(func=cmd_pr)

    pr_cache = pr_sub.add_parser(
        "cache",
        help="Cache PR threads and policy states",
        description="Fetches comment threads and policy evaluations for all PRs and caches them "
        "in ~/.local/cache/gg/. Cleans up cache for completed and abandoned PRs.",
        parents=[common],
    )
    pr_cache.set_defaults(func=cmd_pr)

    pr_show = pr_sub.add_parser(
        "show",
        help="Show PR details with threads and policies",
        description="Displays PR info enriched with cached threads and policy data.",
        parents=[common],
    )
    pr_show.add_argument("pr_id", type=int, help="Pull request ID")
    pr_show.set_defaults(func=cmd_pr)

    pr_review = pr_sub.add_parser(
        "review",
        help="Open PR review files in neovim",
        description="Fetches PR details, produces review files (summary, policies, diff, threads) "
        "in a temporary directory, and opens them in neovim.",
        parents=[common],
    )
    pr_review.add_argument("pr_id", type=int, help="Pull request ID")
    pr_review.set_defaults(func=cmd_pr)

    pr_respond = pr_sub.add_parser(
        "respond",
        help="Post a response to a PR comment thread",
        description="Posts a response to an Azure DevOps PR thread. Called from nvim via :PR post.",
        parents=[common],
    )
    pr_respond.add_argument("pr_id", type=int, help="Pull request ID")
    pr_respond.add_argument("thread_id", type=int, help="Thread ID")
    pr_respond.add_argument("thread_file", help="Path to the thread markdown file")
    pr_respond.set_defaults(func=cmd_pr)

    pr_manage = pr_sub.add_parser(
        "manage",
        help="Manage a pull request in neovim",
        description="Opens a management view for a pull request in neovim. "
        "Provides keymaps to edit title/description and publish changes.",
        parents=[common],
    )
    pr_manage.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage.set_defaults(func=cmd_pr)

    pr_fetch_summary = pr_sub.add_parser(
        "_fetch-summary",
        help="(internal) Fetch or create PR summary file",
        description="Creates summary.md if it doesn't exist and prints JSON result. "
        "Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_fetch_summary.add_argument("pr_id", type=int, help="Pull request ID")
    pr_fetch_summary.set_defaults(func=cmd_pr)

    pr_publish_data = pr_sub.add_parser(
        "_publish",
        help="(internal) Publish PR title/description changes",
        description="Reads staged PR metadata, status, and thread responses, then publishes changes to Azure DevOps. "
        "Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_publish_data.add_argument("pr_id", type=int, help="Pull request ID")
    pr_publish_data.set_defaults(func=cmd_pr)

    pr_sync = pr_sub.add_parser(
        "_manage",
        help="(internal) Reconcile PR state and return view data",
        description="Reads pr.json and summary.md, compares them, and returns current title, "
        "description lines, pending thread responses, and whether changes exist. Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_sync.add_argument("pr_id", type=int, help="Pull request ID")
    pr_sync.set_defaults(func=cmd_pr)

    pr_reload = pr_sub.add_parser(
        "_manage-reload",
        help="(internal) Reload PR details",
        description="Fetches current PR details, writes pr.json, and drops pending summary/status changes. "
        "Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_reload.add_argument("pr_id", type=int, help="Pull request ID")
    pr_reload.set_defaults(func=cmd_pr)

    pr_set_status = pr_sub.add_parser(
        "_set-status",
        help="(internal) Set PR status",
        description="Writes the desired PR status to status.txt in the cache directory. "
        "Called from neovim PR management buffer",
        parents=[common],
    )
    pr_set_status.add_argument("pr_id", type=int, help="Pull request ID")
    pr_set_status.add_argument("status", help="New status value")
    pr_set_status.set_defaults(func=cmd_pr)

    pr_set_vote = pr_sub.add_parser(
        "_set-vote",
        help="(internal) Set PR reviewer vote",
        description="Writes the desired reviewer vote action to vote.txt in the cache directory. "
        "Called from neovim PR management buffer",
        parents=[common],
    )
    pr_set_vote.add_argument("pr_id", type=int, help="Pull request ID")
    pr_set_vote.add_argument(
        "vote",
        choices=(
            "approve",
            "approve with suggestion",
            "reset",
            "wait for author",
            "reject",
            "abstain",
        ),
        help="Vote action",
    )
    pr_set_vote.set_defaults(func=cmd_pr)

    pr_manage_changes = pr_sub.add_parser(
        "_manage-changes",
        help="(internal) Compute and cache PR diff stats",
        description="Fetches source and target branches, then computes diff stats between them. "
        "Writes changes.json and prints JSON result. Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_changes.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_changes.set_defaults(func=cmd_pr)

    pr_manage_diff_open = pr_sub.add_parser(
        "_manage-diff-open",
        help="(internal) Open PR diff with thread annotations",
        description="Generates a PR diff file and returns thread annotation positions. "
        "Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_diff_open.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_diff_open.set_defaults(func=cmd_pr)

    pr_manage_threads = pr_sub.add_parser(
        "_manage-threads",
        help="(internal) Fetch and cache PR threads",
        description="Fetches pull request threads, filters system-only threads, writes threads.json, "
        "and prints JSON result. Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_threads.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_threads.set_defaults(func=cmd_pr)

    pr_manage_thread_open = pr_sub.add_parser(
        "_manage-thread-open",
        help="(internal) Open a PR thread response draft",
        description="Creates or opens a PR thread response draft. Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_thread_open.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_thread_open.add_argument("thread_id", type=int, help="Thread ID")
    pr_manage_thread_open.set_defaults(func=cmd_pr)

    pr_manage_thread_status = pr_sub.add_parser(
        "_manage-thread-status",
        help="(internal) Stage a PR thread status change",
        description="Updates a thread draft status locally so it can be published later. "
        "Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_thread_status.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_thread_status.add_argument("thread_id", help="Thread ID or draft ID")
    pr_manage_thread_status.add_argument(
        "status", choices=("active", "fixed", "wontFix", "closed")
    )
    pr_manage_thread_status.set_defaults(func=cmd_pr)

    pr_manage_thread_new = pr_sub.add_parser(
        "_manage-thread-new",
        help="(internal) Create a PR thread draft",
        description="Creates a new PR thread draft, optionally at a diff location. "
        "Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_thread_new.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_thread_new.add_argument("--file-path", help="Thread file path")
    pr_manage_thread_new.add_argument("--side", choices=("left", "right"), help="Diff side")
    pr_manage_thread_new.add_argument("--line", type=int, help="File line number")
    pr_manage_thread_new.set_defaults(func=cmd_pr)

    pr_manage_policies = pr_sub.add_parser(
        "_manage-policies",
        help="(internal) Fetch and cache PR policies",
        description="Fetches pull request policies, filters to required policies, writes policies.json, "
        "and prints JSON result. Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_policies.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_policies.set_defaults(func=cmd_pr)

    pr_manage_policy_queue = pr_sub.add_parser(
        "_manage-policy-queue",
        help="(internal) Queue a PR policy evaluation",
        description="Queues a pull request policy evaluation. Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_policy_queue.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_policy_queue.add_argument("policy_id", help="Policy configuration ID")
    pr_manage_policy_queue.set_defaults(func=cmd_pr)

    pr_manage_policy_cancel = pr_sub.add_parser(
        "_manage-policy-cancel",
        help="(internal) Cancel a PR policy build",
        description="Cancels the build associated with a pull request policy evaluation. "
        "Called from neovim PR management buffer.",
        parents=[common],
    )
    pr_manage_policy_cancel.add_argument("pr_id", type=int, help="Pull request ID")
    pr_manage_policy_cancel.add_argument("policy_id", help="Policy configuration ID")
    pr_manage_policy_cancel.set_defaults(func=cmd_pr)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
