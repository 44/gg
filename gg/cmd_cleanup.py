import sys

from rich.console import Console

from .utils import (
    get_current_branch,
    get_default_branch,
    get_local_branches,
    run,
)

console = Console(highlight=False)


def get_all_local_branches():
    result = run(["git", "branch", "--format=%(refname:short)"])
    if result.returncode != 0:
        return []

    branches = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            branches.append(line)
    return branches


def is_merged_into(branch, target):
    result = run(["git", "merge-base", "--is-ancestor", branch, target])
    return result.returncode == 0


def has_commits_ahead(branch, target):
    result = run(["git", "rev-list", "--count", f"{branch}--not", target])
    if result.returncode == 0:
        count = int(result.stdout.strip())
        return count > 0
    return False


def cmd_cleanup(args):
    dry_run = args.dry_run
    force = args.force

    default_branch = get_default_branch()
    if not default_branch:
        print("Could not determine default branch", file=sys.stderr)
        return 1

    branches = get_local_branches()
    all_branches = get_all_local_branches()
    current_branch = get_current_branch()

    branches_no_upstream = [
        b for b in all_branches if b not in [br for br, _ in branches]
    ]

    deleted = 0
    skipped = 0

    for branch in branches_no_upstream:
        if branch == current_branch:
            skipped += 1
            continue

        if branch == default_branch:
            skipped += 1
            continue

        if is_merged_into(branch, default_branch):
            if has_commits_ahead(branch, default_branch):
                console.print(
                    f"[yellow]skipped[/yellow]\t{branch} - has commits not in {default_branch}"
                )
                skipped += 1
            else:
                if dry_run:
                    console.print(
                        f"[cyan]would delete[/cyan]\t{branch} - merged into {default_branch}"
                    )
                else:
                    result = run(["git", "branch", "-d", branch])
                    if result.returncode == 0:
                        console.print(
                            f"[green]deleted[/green]\t{branch} - merged into {default_branch}"
                        )
                        deleted += 1
                    else:
                        console.print(
                            f"[red]failed[/red]\t{branch}: {result.stderr.strip()}"
                        )
                        if not force:
                            skipped += 1
                            continue
                        result = run(["git", "branch", "-D", branch])
                        if result.returncode == 0:
                            console.print(
                                f"[green]deleted (force)[/green]\t{branch} - merged into {default_branch}"
                            )
                            deleted += 1
                        else:
                            console.print(
                                f"[red]failed (force)[/red]\t{branch}: {result.stderr.strip()}"
                            )
                            skipped += 1
        else:
            skipped += 1

    print(f"\nDone. Deleted {deleted} branch(es), skipped {skipped}", file=sys.stderr)
    return 0
