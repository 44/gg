import os
import platform
import stat
import subprocess
import sys

REPO_URL = "git+https://github.com/44/gg"

COMMANDS = ["fff", "mb", "ms", "party", "pff", "wc", "rb", "cleanup"]


def _get_bin_dir():
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("USERPROFILE", ""), ".local", "bin")
    return os.path.join(os.path.expanduser("~"), ".local", "bin")


def _run(cmd, quiet):
    if not quiet:
        print(f"Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    return result


def cmd_install(args):
    quiet = args.quiet
    bin_dir = _get_bin_dir()

    _run(["uv", "tool", "install", "--no-config", "--from", REPO_URL, "gg"], quiet)

    if not quiet:
        print(f"Installing gg command wrappers to {bin_dir}", file=sys.stderr)

    os.makedirs(bin_dir, exist_ok=True)

    for cmd in COMMANDS:
        script_path = os.path.join(bin_dir, f"git-{cmd}")
        script_content = f"""#!/bin/sh
exec gg {cmd} "$@"
"""

        try:
            with open(script_path, "w") as f:
                f.write(script_content)

            st = os.stat(script_path)
            os.chmod(script_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

            if not quiet:
                print(f"Installed: {script_path}", file=sys.stderr)
        except OSError as e:
            print(f"Failed to install {cmd}: {e}", file=sys.stderr)
            return 1

    if not quiet:
        print(f"\nMake sure {bin_dir} is in your PATH.", file=sys.stderr)

    return 0
