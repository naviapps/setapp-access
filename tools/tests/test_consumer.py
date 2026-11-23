"""Protect the fixture's separation from auto-initializing vendor code."""

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ConsumerBoundaryTests(unittest.TestCase):
    def test_checks_execute_only_the_vendor_free_product(self):
        config = tomllib.loads((ROOT / "sdk-checks.toml").read_text(encoding="utf-8"))["swift"]
        self.assertTrue(config["verify_dependencies"])
        self.assertEqual(config["build_system"], "swiftbuild")
        self.assertEqual(config["executable"], "SetappSnapshotConsumer")
        self.assertNotIn("executables", config)

    def test_fixture_declares_no_path_from_runtime_to_vendor_adapter(self):
        fixture = ROOT / "fixtures/swift-consumer"
        manifest = (fixture / "Package.swift").read_text()
        runtime = manifest.split(".executableTarget(", 1)[1].split(".target(", 1)[0]
        self.assertEqual(manifest.count(".executableTarget("), 1)
        self.assertIn('name: "SetappSnapshotConsumer"', runtime)
        self.assertIn('.product(name: "SetappAccess",', runtime)
        self.assertNotIn("SetappAccessMacOS", runtime)
        self.assertNotIn("SetappMacOSCompileOnly", runtime)
        self.assertNotIn(".dynamic", manifest)
        self.assertIn(
            '.library(name: "SetappMacOSCompileOnly", targets: ["SetappMacOSCompileOnly"])',
            manifest,
        )
        source = (fixture / "Sources/SetappSnapshotConsumer/Consumer.swift").read_text()
        imports = [line for line in source.splitlines() if line.startswith("import ")]
        self.assertEqual(imports, ["import Foundation", "import SetappAccess"])


if __name__ == "__main__":
    unittest.main()
