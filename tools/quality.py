"""Check or format the Swift, Python, and documentation sources in this repository."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, env=None):
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["check", "format"])
    write = parser.parse_args().operation == "format"
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
    )
    files = []
    for file in sorted(set(os.fsdecode(tracked).split("\0")) - {""}):
        path = ROOT / file
        if not path.is_file():
            continue
        if path.resolve(strict=True) != path:
            raise ValueError(f"Source checks require ordinary repository files: {file}")
        files.append("./" + file)
    python = [file for file in files if file.endswith(".py")]
    docs = [
        file
        for file in files
        if Path(file).suffix in {".json", ".md", ".toml", ".yaml", ".yml"}
        and "fixtures" not in Path(file).parts
        and not Path(file).name.upper().startswith(("CHANGELOG", "HISTORY"))
    ]
    swift = [file for file in files if file.endswith(".swift")]
    workflows = [
        file
        for file in files
        if file.startswith("./.github/workflows/") and file.endswith((".yaml", ".yml"))
    ]

    if not write:
        run("ruff", "check", *python)
    run("ruff", "format", *([] if write else ["--check"]), *python)
    run("dprint", "fmt" if write else "check", "--config", ".dprint.json", *docs)

    if sys.platform == "darwin":
        if write:
            run("xcrun", "swift-format", "format", "--in-place", "--parallel", *swift)
        else:
            run("xcrun", "swift-format", "lint", "--strict", "--parallel", *swift)
            env = dict(os.environ, SCRIPT_INPUT_FILE_COUNT=str(len(swift)))
            env.update({f"SCRIPT_INPUT_FILE_{i}": str(ROOT / path) for i, path in enumerate(swift)})
            run(
                "swiftlint",
                "lint",
                "--strict",
                "--quiet",
                "--disable-sourcekit",
                "--config",
                ".swiftlint.yml",
                "--use-script-input-files",
                env=env,
            )

    if not write:
        shellcheck = shutil.which("shellcheck")
        if not shellcheck:
            raise RuntimeError(
                "ShellCheck is required to check workflow scripts. Run mise install."
            )
        run("actionlint", f"-shellcheck={shellcheck}", "-pyflakes=", *workflows)


if __name__ == "__main__":
    main()
