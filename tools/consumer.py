#!/usr/bin/env python3
"""Run the vendor-free external consumer and compile the separate macOS target."""

from pathlib import Path

from _tooling import load

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    load("consumers").check_swift(
        root=ROOT,
        inputs=("Package.swift", "Sources", "Tests", "Notices", "LICENSE"),
        fixture=ROOT / "fixtures/swift-consumer",
        executables=("SetappSnapshotConsumer",),
        argv=argv,
    )


if __name__ == "__main__":
    main()
