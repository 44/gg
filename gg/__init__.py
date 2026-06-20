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
        "Wrappers use 'uvx --offline' to run the locally installed tool. Overwrites existing scripts.",
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

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
