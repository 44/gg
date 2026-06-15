import sys

from rich.console import Console

from .utils import (
    format_status,
    get_ahead_behind,
    get_local_branches,
    run,
)

console = Console(highlight=False)


def cmd_pff(args):
    quiet = args.quiet

    branches = get_local_branches()

    if not branches:
        print("No local branches with upstream configured", file=sys.stderr)
        return 0

    updated = 0
    for branch, upstream in branches:
        ahead, behind = get_ahead_behind(branch, upstream)
        if ahead > 0 and behind == 0:
            remote = upstream.split("/", 1)[0] if "/" in upstream else None
            if not remote:
                continue
            result = run(["git", "push", remote, branch])
            if result.returncode == 0:
                console.print(
                    f"[green]pushed[/green]\t{branch} {upstream}\t{format_status(ahead, behind)}"
                )
                updated += 1
            else:
                print(
                    f"error\t{branch} {upstream}: {result.stderr.strip()}",
                    file=sys.stderr,
                )
        elif ahead > 0 or behind > 0:
            console.print(
                f"[red]skipped[/red]\t{branch} {upstream}\t{format_status(ahead, behind)}"
            )

    if not quiet:
        print(f"\nDone. Pushed {updated} branch(es)", file=sys.stderr)
    return 0
