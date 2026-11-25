"""Protect the fixture's separation from auto-initializing vendor code."""

import json
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def manifest(path):
    with tempfile.TemporaryDirectory(prefix="setapp-package-graph-") as scratch:
        return json.loads(
            subprocess.check_output(
                [
                    "/usr/bin/xcrun",
                    "swift",
                    "package",
                    "--package-path",
                    str(path),
                    "--scratch-path",
                    scratch,
                    "--manifest-cache",
                    "none",
                    "dump-package",
                ],
                timeout=30,
            )
        )


class ConsumerBoundaryTests(unittest.TestCase):
    def test_checks_execute_only_the_vendor_free_product(self):
        manifest = tomllib.loads((ROOT / "sdk-tooling.toml").read_text(encoding="utf-8"))
        config = manifest["checks"]["swift"]
        self.assertTrue(config["verify_dependencies"])
        self.assertEqual(config["build_system"], "swiftbuild")
        self.assertEqual(config["executable"], "SetappSnapshotConsumer")
        self.assertNotIn("executables", config)

    def test_fixture_declares_no_path_from_runtime_to_vendor_adapter(self):
        fixture = manifest(ROOT / "fixtures/consumers/swift")
        runtimes = [target for target in fixture["targets"] if target["type"] == "executable"]
        self.assertEqual([target["name"] for target in runtimes], ["SetappSnapshotConsumer"])
        self.assertEqual(
            runtimes[0]["dependencies"],
            [{"product": ["SetappAccess", "setapp-access", None, None]}],
        )
        self.assertEqual(
            [product["type"] for product in fixture["products"]], [{"library": ["automatic"]}]
        )

        sdk = manifest(ROOT)
        targets = {target["name"]: target for target in sdk["targets"]}
        products = {product["name"]: product for product in sdk["products"]}
        self.assertEqual(products["SetappAccess"]["targets"], ["SetappAccess"])
        self.assertEqual(targets["SetappAccess"]["dependencies"], [])
        self.assertEqual(
            [target["dependencies"] for target in sdk["targets"] if target["type"] == "test"],
            [[{"byName": ["SetappAccess", None]}]],
        )


if __name__ == "__main__":
    unittest.main()
