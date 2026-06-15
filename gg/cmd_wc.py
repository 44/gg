import sys

from rich.console import Console

from .utils import get_default_branch, run

console = Console(highlight=False)


def cmd_wc(args):
    diff_spec = args.diff_spec

    if not diff_spec:
        default_branch = get_default_branch()
        if not default_branch:
            print(
                "Error: could not determine default branch (main/master)",
                file=sys.stderr,
            )
            return 1
        diff_spec = f"origin/{default_branch}...HEAD"

    name_status_result = run(["git", "diff", "--name-status", diff_spec])
    if name_status_result.returncode != 0:
        print(
            f"Error running git diff --name-status: {name_status_result.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    numstat_result = run(["git", "diff", "--numstat", diff_spec])
    if numstat_result.returncode != 0:
        print(
            f"Error running git diff --numstat: {numstat_result.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    name_status_lines = (
        name_status_result.stdout.strip().split("\n")
        if name_status_result.stdout.strip()
        else []
    )
    numstat_lines = (
        numstat_result.stdout.strip().split("\n")
        if numstat_result.stdout.strip()
        else []
    )

    status_map = {
        "A": "[green]A[/green]",
        "D": "[red]D[/red]",
        "M": "[yellow]M[/yellow]",
        "R": "[cyan]R[/cyan]",
        "C": "[blue]C[/blue]",
    }

    total_added = 0
    total_deleted = 0
    total_files = 0
    for i, name_line in enumerate(name_status_lines):
        if not name_line:
            continue
        parts = name_line.split(None, 1)
        if len(parts) < 2:
            continue
        status_code = parts[0]
        filename = parts[1]

        added = "0"
        deleted = "0"
        if i < len(numstat_lines) and numstat_lines[i]:
            num_parts = numstat_lines[i].split("\t")
            if len(num_parts) >= 2:
                added = num_parts[0]
                deleted = num_parts[1]

        if added != "-":
            total_added += int(added)
        if deleted != "-":
            total_deleted += int(deleted)
        total_files += 1

        colored_status = status_map.get(status_code, status_code)

        counts = []
        if added != "-" and added != "0":
            counts.append(f"[green]+{added}[/green]")
        if deleted != "-" and deleted != "0":
            counts.append(f"[red]-{deleted}[/red]")

        counts_str = " ".join(counts)
        console.print(f"{colored_status}  {filename}  {counts_str}")

    console.print(
        f"\n{total_files} files changed [green]+{total_added}[/green] [red]-{total_deleted}[/red]"
    )

    return 0
