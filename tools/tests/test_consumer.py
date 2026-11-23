"""Protect the fixture's declared separation from auto-initializing vendor code."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
specification = importlib.util.spec_from_file_location(
    "setapp_consumer", ROOT / "tools/consumer.py"
)
consumer = importlib.util.module_from_spec(specification)
specification.loader.exec_module(consumer)


class ConsumerBoundaryTests(unittest.TestCase):
    def test_driver_runs_only_the_vendor_free_executable(self):
        def fake_run(command, *, cwd, env, **kwargs):
            sdk = cwd.parent / "sdk"
            self.assertEqual(
                {path.name for path in sdk.iterdir()},
                {"Package.swift", "Sources", "Tests", "Notices", "LICENSE"},
            )
            self.assertEqual(Path(env["GIT_CONFIG_GLOBAL"]).read_bytes(), git_config.read_bytes())
            self.assertTrue(Path(env["XDG_CACHE_HOME"]).is_relative_to(cwd.parent))
            self.assertEqual(
                (cwd / ".swiftpm/configuration/mirrors.json").read_bytes(), mirrors.read_bytes()
            )
            if "show-dependencies" in command:
                return SimpleNamespace(
                    stdout=json.dumps(
                        {
                            "path": str(cwd),
                            "dependencies": [{"path": str(sdk), "dependencies": []}],
                        }
                    )
                )
            if "--show-bin-path" in command:
                build = Path(command[command.index("--scratch-path") + 1])
                build.mkdir()
                (build / "SetappSnapshotConsumer").touch()
                (build / "SetappMacOSCompileOnly").touch()
                return SimpleNamespace(stdout=str(build))
            return None

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            git_config = work / "gitconfig"
            git_config.write_text("[core]\n\tautocrlf = false\n")
            mirrors = work / "mirrors.json"
            mirrors.write_text("{}")
            with patch.object(consumer.subprocess, "run", side_effect=fake_run) as run:
                consumer.main(
                    [
                        "--git-config",
                        str(git_config),
                        "--mirror-config",
                        str(mirrors),
                        "--allow-warnings",
                    ]
                )
                commands = [call.args[0] for call in run.call_args_list]
                self.assertEqual(len(commands), 4)
                self.assertEqual(commands[1][2], "build")
                self.assertIn("swiftbuild", commands[1])
                self.assertNotIn("-warnings-as-errors", commands[1])
                self.assertEqual(
                    [Path(name).name for name in commands[3]], ["SetappSnapshotConsumer"]
                )

    def test_rejects_links_to_source_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sdk = root / "source"
            sdk.mkdir()
            original = root / "source.txt"
            original.touch()
            (sdk / "Package.swift").symlink_to(original)
            with self.assertRaisesRegex(ValueError, "escapes the staged package"):
                consumer.stage_package(sdk, root / "staged", ("Package.swift",))

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
