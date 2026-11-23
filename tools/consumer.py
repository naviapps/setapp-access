#!/usr/bin/env python3
"""Run the external snapshot consumer and compile the macOS adapter."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/swift-consumer"
SDK_INPUTS = ("Package.swift", "Sources", "Tests", "Notices", "LICENSE")
FIXTURE_INPUTS = ("Package.swift", "Sources")
CACHE_DIRECTORIES = (".git", ".build", ".swiftpm", "__pycache__")


def stage_package(source, destination, inputs):
    destination.mkdir()
    for name in inputs:
        origin = source / name
        target = destination / name
        if origin.is_dir() and not origin.is_symlink():
            shutil.copytree(
                origin, target, symlinks=True, ignore=shutil.ignore_patterns(*CACHE_DIRECTORIES)
            )
        else:
            shutil.copy2(origin, target, follow_symlinks=False)
    for path in destination.rglob("*"):
        if path.is_symlink() and (
            Path(os.readlink(path)).is_absolute()
            or not path.resolve(strict=True).is_relative_to(destination)
        ):
            raise ValueError(f"Consumer input escapes the staged package: {path}")


def copy_policy(destination, *candidates):
    policies = [candidate.read_bytes() for candidate in candidates if candidate.exists()]
    if not policies:
        return False
    if any(policy != policies[0] for policy in policies[1:]):
        raise ValueError(f"Conflicting dependency policy: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(policies[0])
    return True


def isolated_environment(work, git_config):
    # Xcode's mounted developer components depend on the original home directory.
    env = {
        key: os.environ[key]
        for key in (
            "HOME",
            "CFFIXED_USER_HOME",
            "DEVELOPER_DIR",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "TZ",
            "TERM",
            "NO_COLOR",
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
        )
        if key in os.environ
    }
    for key, name in {
        "XDG_CACHE_HOME": "cache",
        "XDG_CONFIG_HOME": "config",
        "TMPDIR": "tmp",
        "CLANG_MODULE_CACHE_PATH": "module-cache",
        "SWIFT_MODULECACHE_PATH": "module-cache",
    }.items():
        path = work / name
        path.mkdir(exist_ok=True)
        env[key] = str(path)
    configuration = work / "gitconfig"
    git_config = git_config or os.environ.get("GIT_CONFIG_GLOBAL")
    configuration.write_bytes(Path(git_config).read_bytes() if git_config else b"")
    return dict(
        env,
        PATH="/usr/bin:/bin:/usr/sbin:/sbin",
        GIT_CONFIG_GLOBAL=str(configuration),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
    )


def check_dependencies(dependency, allowed_roots):
    path = Path(dependency["path"]).resolve(strict=True)
    if not any(path.is_relative_to(root) for root in allowed_roots):
        raise ValueError(f"Swift consumer dependency escapes the staged package: {path}")
    for child in dependency["dependencies"]:
        check_dependencies(child, allowed_roots)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-config", type=Path, help="Explicit Git rewrites for dependencies")
    parser.add_argument("--mirror-config", type=Path, help="Explicit SwiftPM mirrors.json")
    parser.add_argument("--build-system", choices=("native", "swiftbuild"), default="swiftbuild")
    parser.add_argument("--allow-warnings", action="store_true", help="Allow Swift warnings")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="setapp-consumer-") as directory:
        work = Path(directory).resolve()
        sdk, consumer = work / "sdk", work / "consumer"
        stage_package(ROOT, sdk, SDK_INPUTS)
        stage_package(FIXTURE, consumer, FIXTURE_INPUTS)

        pinned = copy_policy(
            consumer / "Package.resolved", ROOT / "Package.resolved", FIXTURE / "Package.resolved"
        )
        mirrors = Path(".swiftpm/configuration/mirrors.json")
        explicit_mirrors = [args.mirror_config.resolve(strict=True)] if args.mirror_config else []
        copy_policy(consumer / mirrors, ROOT / mirrors, FIXTURE / mirrors, *explicit_mirrors)

        env = isolated_environment(work, args.git_config)
        scratch = work / "scratch"
        swift = ["/usr/bin/xcrun", "swift"]
        common = [
            "--scratch-path",
            str(scratch),
            "--cache-path",
            str(work / "swiftpm-cache"),
            "--config-path",
            str(work / "swiftpm-config"),
            "--security-path",
            str(work / "swiftpm-security"),
            "--disable-dependency-cache",
            "--manifest-cache",
            "none",
            "--build-system",
            args.build_system,
            "-Xswiftc",
            "-strict-concurrency=complete",
        ]
        if not args.allow_warnings:
            common.extend(("-Xswiftc", "-warnings-as-errors"))
        if pinned:
            common.append("--force-resolved-versions")

        def run(command, *, capture_output=False):
            return subprocess.run(
                command,
                cwd=consumer,
                env=env,
                check=True,
                text=True,
                stdout=subprocess.PIPE if capture_output else None,
            )

        graph = run(
            [*swift, "package", *common, "show-dependencies", "--format", "json"],
            capture_output=True,
        )
        # Reject absolute package paths outside the two staged packages and their dependencies.
        check_dependencies(json.loads(graph.stdout), (consumer, sdk, scratch))
        build = [*swift, "build", *common]
        run(build)
        result = run([*build, "--show-bin-path"], capture_output=True)
        binary = (Path(result.stdout.strip()) / "SetappSnapshotConsumer").resolve(strict=True)
        if not binary.is_relative_to(scratch):
            raise ValueError(f"Swift consumer executable escapes its scratch tree: {binary}")
        run([str(binary)])


if __name__ == "__main__":
    main()
