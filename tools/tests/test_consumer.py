"""Protect the fixture's declared separation from auto-initializing vendor code."""

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
specification = importlib.util.spec_from_file_location(
    "setapp_consumer", ROOT / "tools/consumer.py"
)
consumer = importlib.util.module_from_spec(specification)
specification.loader.exec_module(consumer)


class ConsumerBoundaryTests(unittest.TestCase):
    def test_driver_runs_only_the_vendor_free_executable(self):
        with patch.object(consumer, "load") as load:
            consumer.main(["--mirror-config", "/job/mirrors.json"])
        self.assertEqual(load.call_args.args, ("consumers",))
        options = load.return_value.check_swift.call_args.kwargs
        self.assertEqual(options["executables"], ("SetappSnapshotConsumer",))
        self.assertEqual(
            options["inputs"], ("Package.swift", "Sources", "Tests", "Notices", "LICENSE")
        )
        self.assertEqual(options["argv"], ["--mirror-config", "/job/mirrors.json"])

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
