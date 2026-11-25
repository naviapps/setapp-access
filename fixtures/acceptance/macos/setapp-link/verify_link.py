#!/usr/bin/env python3
"""Build and inspect a disposable Setapp adapter app in an owned macOS lease."""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent
ROOT = FIXTURE.parents[3]
PRODUCT = "SetappLinkProbe"
VENDOR = "Setapp-framework"
VERSION = "5.5.6"
REVISION = "3510910bbb40987d617c2d8ddc1c90383c712964"
ARCHIVE = Path("Setapp.xcframework/macos-arm64_x86_64/libSetapp.a")
ARCHIVE_BLOB = "3359eef0ea0847d0870aa03d813e93660934f1bc"
NOTICE_BLOB = "f26f25dfd51d19bc3d4df4829802abecb885806a"
RESOURCES = Path("Sources/SetappResources/Resources/Bundles/SetappFramework-Resources.bundle")
RESOURCE_PRODUCT = "Setapp_SetappResources.bundle"
RESOURCE_IDENTIFIER = "setapp-framework.SetappResources.resources"
ADHOC_METADATA = {
    "Contents/Info.plist",
    "Contents/_CodeSignature/CodeDirectory",
    "Contents/_CodeSignature/CodeRequirements",
    "Contents/_CodeSignature/CodeResources",
    "Contents/_CodeSignature/CodeSignature",
}
NOTICE = Path("Notices/Setapp.txt")
PLIST = {
    "CFBundleExecutable": PRODUCT,
    "CFBundleIdentifier": "com.example.SetappLinkProbe-setapp",
    "CFBundleName": PRODUCT,
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "1.0",
    "CFBundleVersion": "1",
    "LSMinimumSystemVersion": "26.0",
    "MPSupportedArchitectures": ["arm64"],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def owned_lease(lease_id):
    require(str(uuid.UUID(lease_id)) == lease_id, "Expected a canonical workspace lease UUID")
    root = Path("/tmp").resolve() / ("workspace-" + lease_id)
    require(
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and os.geteuid() != 0
        and root.is_dir()
        and not root.is_symlink()
        and root.stat().st_uid == os.getuid()
        and not root.stat().st_mode & 0o077
        and json.loads(regular_bytes(root / "lease.json")) == {"lease": lease_id},
        "The link fixture requires a private owned macOS workspace",
    )
    model = subprocess.check_output(["/usr/sbin/sysctl", "-n", "hw.model"], text=True).strip()
    require(model.startswith("VirtualMac"), "The link fixture requires a macOS virtual machine")
    return root


def regular_bytes(path):
    require(path.is_file() and not path.is_symlink(), f"Expected a regular file: {path.name}")
    return path.read_bytes()


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), f"Expected a directory: {root.name}")
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"Symlink in app input or payload: {path.relative_to(root)}")
        if not path.is_dir():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(
                regular_bytes(path)
            ).hexdigest()
    return result


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def copy_input(source, destination):
    require(source.resolve(strict=True) == source, f"Input crosses a symlink: {source.name}")
    if source.is_dir():
        inventory(source)
        shutil.copytree(source, destination, symlinks=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        require(
            source.is_file() and not source.is_symlink(), f"Expected a regular file: {source.name}"
        )
        shutil.copy2(source, destination, follow_symlinks=False)


class ResourceMetadataError(ValueError):
    def __init__(self, reason, files, count):
        super().__init__("Unexpected files beside the vendor resource bundle")
        self.diagnostic = {
            "reason": reason,
            "fileCount": count,
            "files": files,
            "truncated": count > len(files),
        }


def metadata_records(root, names, records):
    result = []
    for name in sorted(names)[:8]:
        row = {"bytes": (root / name).stat().st_size, "sha256": records[name]}
        if re.fullmatch(r"[A-Za-z0-9._/-]{1,160}", name):
            row["path"] = name
        else:
            row["pathSHA256"] = hashlib.sha256(os.fsencode(name)).hexdigest()
        result.append(row)
    return result


def verify_adhoc_resource_bundle(root):
    info = plistlib.loads(regular_bytes(root / "Contents/Info.plist"))
    require(
        isinstance(info, dict)
        and info.get("CFBundleIdentifier") == RESOURCE_IDENTIFIER
        and info.get("CFBundleName") == RESOURCE_PRODUCT.removesuffix(".bundle")
        and info.get("CFBundlePackageType") == "BNDL"
        and "CFBundleExecutable" not in info,
        "Unexpected generated resource bundle metadata",
    )
    require(
        (root / "Contents/_CodeSignature/CodeSignature").stat().st_size == 0,
        "Unexpected CMS signature in the resource-only bundle",
    )
    display = subprocess.run(
        ["/usr/bin/codesign", "--display", "--verbose=4", str(root)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    fields = display.stderr.splitlines()
    for key, expected in (
        ("Identifier", RESOURCE_IDENTIFIER),
        ("Format", "bundle"),
        ("Signature", "adhoc"),
        ("TeamIdentifier", "not set"),
    ):
        require(
            [line for line in fields if line.startswith(key + "=")] == [key + "=" + expected],
            "Unexpected generated resource bundle signature identity",
        )
    require(
        not any(line.startswith("Authority=") for line in fields), "Unexpected signing authority"
    )
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--strict", str(root)],
        check=True,
        capture_output=True,
        timeout=30,
    )


def inspect_resource_metadata(root, nested_prefix, records, resource_files):
    metadata = set(records) - {f"{nested_prefix}/{name}" for name in resource_files}
    files = metadata_records(root, metadata, records)
    if metadata in (set(), {"Info.plist"}, {"Contents/Info.plist"}):
        try:
            if metadata:
                info = plistlib.loads(regular_bytes(root / next(iter(metadata))))
                require(
                    isinstance(info, dict) and "CFBundleExecutable" not in info,
                    "Unexpected resource bundle executable",
                )
        except (ValueError, OSError) as error:
            raise ResourceMetadataError("invalid-wrapper-plist", files, len(metadata)) from error
        return {"signature": "unsigned", "files": files}

    # Swift Build can sign the resource-only wrapper without a signing identity.
    # Keep the path set exact and verify the staged copy's actual seal.
    if metadata != ADHOC_METADATA or nested_prefix != f"Contents/Resources/{RESOURCES.name}":
        raise ResourceMetadataError("unexpected-paths", files, len(metadata))
    try:
        verify_adhoc_resource_bundle(root)
    except (ValueError, OSError, subprocess.SubprocessError):
        raise ResourceMetadataError("adhoc-verification-failed", files, len(metadata)) from None
    return {"signature": "adhoc-verified", "files": files}


def inspect_payload(app, vendor, sdk_notice):
    records = inventory(app)
    contents = app / "Contents"
    require(plistlib.loads(regular_bytes(contents / "Info.plist")) == PLIST, "App metadata differs")
    resource_root = contents / "Resources" / RESOURCE_PRODUCT
    nested_bundles = list(resource_root.rglob(RESOURCES.name))
    require(len(nested_bundles) == 1, "Expected exactly one copied vendor resource bundle")
    nested = nested_bundles[0]
    resource_files = inventory(nested)
    require(
        resource_files and resource_files == inventory(vendor / RESOURCES),
        "Vendor resources differ",
    )
    notice = regular_bytes(contents / "Resources" / NOTICE)
    require(notice == sdk_notice == regular_bytes(vendor / "LICENSE"), "Vendor notice differs")
    expected = {
        "Contents/Info.plist",
        f"Contents/MacOS/{PRODUCT}",
        f"Contents/Resources/{NOTICE.as_posix()}",
    }
    resource_records = inventory(resource_root)
    nested_prefix = nested.relative_to(resource_root).as_posix()
    wrapper = inspect_resource_metadata(
        resource_root, nested_prefix, resource_records, resource_files
    )
    expected.update(f"Contents/Resources/{RESOURCE_PRODUCT}/{name}" for name in resource_records)
    require(set(records) == expected, "App contains files outside the probe payload")
    require((contents / "MacOS" / PRODUCT).stat().st_mode & 0o111, "App executable mode is missing")
    return {
        "resourceFiles": len(resource_files),
        "resourceWrapper": wrapper,
        "resourceTreeSHA256": hashlib.sha256(
            json.dumps(resource_files, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "noticeSHA256": hashlib.sha256(notice).hexdigest(),
    }


def build_and_inspect(lease, work):
    sdk, fixture = work / "sdk", work / "consumer"
    for name in ("Package.swift", "Sources", "Tests", NOTICE):
        copy_input(ROOT / name, sdk / name)
    for name in ("Package.swift", "Sources"):
        copy_input(FIXTURE / name, fixture / name)
    scratch = work / "scratch"
    gitconfig = lease / "gitconfig"
    require(
        gitconfig.is_file() and not gitconfig.is_symlink(), "Expected the lease Git source policy"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "CFFIXED_USER_HOME", "DEVELOPER_DIR", "LANG", "LC_ALL", "LC_CTYPE"}
    }
    env.update(
        PATH="/usr/bin:/bin:/usr/sbin:/sbin",
        TMPDIR=str(work / "tmp"),
        CLANG_MODULE_CACHE_PATH=str(work / "module-cache"),
        SWIFT_MODULECACHE_PATH=str(work / "module-cache"),
        XDG_CACHE_HOME=str(work / "cache"),
        XDG_CONFIG_HOME=str(work / "config"),
        GIT_CONFIG_GLOBAL=str(gitconfig),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_ALLOW_PROTOCOL="file",
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="credential.helper",
        GIT_CONFIG_VALUE_0="",
    )
    (work / "tmp").mkdir()
    isolation = [
        "--scratch-path",
        str(scratch),
        "--cache-path",
        str(work / "cache"),
        "--config-path",
        str(work / "config"),
        "--security-path",
        str(work / "security"),
        "--disable-dependency-cache",
        "--disable-netrc",
        "--disable-keychain",
        "--manifest-cache",
        "none",
    ]

    def run(*command, capture=True):
        return subprocess.run(
            command,
            cwd=fixture,
            env=env,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            timeout=600,
        ).stdout

    swift = ("/usr/bin/xcrun", "swift")
    run(*swift, "package", *isolation, "resolve", capture=False)
    pins = json.loads(regular_bytes(fixture / "Package.resolved"))["pins"]
    require(
        len(pins) == 1
        and pins[0]["identity"] == VENDOR.lower()
        and pins[0]["state"] == {"revision": REVISION, "version": VERSION},
        "Resolved vendor identity or revision differs",
    )
    vendor = scratch / "checkouts" / VENDOR
    require(
        vendor.resolve(strict=True) == vendor
        and run("/usr/bin/git", "-C", str(vendor), "rev-parse", "HEAD").strip() == REVISION
        and not run("/usr/bin/git", "-C", str(vendor), "status", "--porcelain"),
        "Expected the exact clean vendor checkout",
    )
    archive = vendor / ARCHIVE
    require(archive.resolve(strict=True) == archive, "Setapp archive leaves its checkout")
    archive_data = regular_bytes(archive)
    sdk_notice = regular_bytes(sdk / NOTICE)
    require(git_blob(archive_data) == ARCHIVE_BLOB, "Official Setapp archive bytes differ")
    require(git_blob(sdk_notice) == NOTICE_BLOB, "Official Setapp license bytes differ")
    build = [
        *swift,
        "build",
        *isolation,
        "--force-resolved-versions",
        "--product",
        PRODUCT,
        "-Xswiftc",
        "-strict-concurrency=complete",
        "-Xswiftc",
        "-warnings-as-errors",
    ]
    bin_path = Path(run(*build, "--show-bin-path").strip()).resolve()
    require(bin_path.is_relative_to(scratch), "SwiftPM output left the owned build tree")
    # SwiftPM adds -lSetapp against its staged archive. Force-load that same
    # path, rather than linking a second copy from the dependency checkout.
    staged_archive = bin_path / ARCHIVE.name
    run(*build, "-Xlinker", "-force_load", "-Xlinker", str(staged_archive), capture=False)
    staged = staged_archive.resolve(strict=True)
    require(
        staged.is_relative_to(scratch) and regular_bytes(staged) == archive_data,
        "SwiftPM staged Setapp archive bytes differ",
    )

    app = work / f"{PRODUCT}.app"
    contents = app / "Contents"
    image = contents / "MacOS" / PRODUCT
    copy_input(bin_path / PRODUCT, image)
    copy_input(bin_path / RESOURCE_PRODUCT, contents / "Resources" / RESOURCE_PRODUCT)
    copy_input(sdk / NOTICE, contents / "Resources" / NOTICE)
    (contents / "Info.plist").write_bytes(plistlib.dumps(PLIST))
    payload = inspect_payload(app, vendor, sdk_notice)
    image_data = regular_bytes(image)
    require(f"__scv__{VERSION}".encode() in image_data, "Setapp static version marker missing")
    require(
        run("/usr/bin/xcrun", "lipo", "-archs", str(image)).split() == ["arm64"],
        "Wrong architecture",
    )
    symbols = run("/usr/bin/xcrun", "nm", "-j", "-U", str(image)).splitlines()
    require(
        any("SetappAccessMacOS" in name and "Session" in name for name in symbols),
        "The linked executable does not define SetappSession symbols",
    )
    dependencies = run("/usr/bin/xcrun", "otool", "-L", str(image)).splitlines()[1:]
    for row in dependencies:
        path = row.strip().split(" (", 1)[0]
        require(
            path.startswith(("/System/Library/", "/usr/lib/"))
            or (path.startswith("@rpath/libswift") and path.endswith(".dylib")),
            f"Unexpected linked dependency: {path}",
        )
    return {
        "vendorRevision": REVISION,
        "forceLoadArchiveSHA256": hashlib.sha256(archive_data).hexdigest(),
        "linkedImageSHA256": hashlib.sha256(image_data).hexdigest(),
        "architecture": "arm64",
        "adapterSymbolsLinked": True,
        "vendorVersionMarker": VERSION,
        "dynamicDependencyCount": len(dependencies),
        **payload,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lease", required=True, help="Owned CI workspace lease UUID")
    lease = owned_lease(parser.parse_args().lease)
    require(ROOT.is_relative_to(lease), "Probe source must be inside the owned workspace")
    try:
        with tempfile.TemporaryDirectory(dir=lease, prefix="setapp-link-") as directory:
            proof = build_and_inspect(lease, Path(directory))
    except ResourceMetadataError as error:
        print("SETAPP_LINK_RESOURCE_METADATA " + json.dumps(error.diagnostic), file=sys.stderr)
        raise SystemExit(str(error)) from None
    print(json.dumps({"result": "passed", "vendorLaunched": False, **proof}, sort_keys=True))


if __name__ == "__main__":
    main()
