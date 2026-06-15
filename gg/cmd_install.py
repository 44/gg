import os
import platform
import stat
import sys

REPO_URL = "git+https://github.com/44/gg"

COMMANDS = ["fff", "mb", "ms", "party", "pff", "wc", "rb", "cleanup"]


def _get_bin_dir():
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("USERPROFILE", ""), "bin")
    return os.path.join(os.path.expanduser("~"), ".local", "bin")


def cmd_install(args):
    quiet = args.quiet
    bin_dir = _get_bin_dir()
    os.makedirs(bin_dir, exist_ok=True)

    if not quiet:
        print(f"Installing gg commands to {bin_dir}", file=sys.stderr)

    is_windows = platform.system() == "Windows"

    for cmd in COMMANDS:
        if is_windows:
            script_path = os.path.join(bin_dir, f"git-{cmd}.cmd")
            script_content = f"""@echo off
uvx --no-config --from {REPO_URL} gg {cmd} %*
"""
        else:
            script_path = os.path.join(bin_dir, f"git-{cmd}")
            script_content = f"""#!/bin/sh
exec uvx --no-config --from {REPO_URL} gg {cmd} "$@"
"""

        try:
            with open(script_path, "w") as f:
                f.write(script_content)

            if not is_windows:
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
