"""Offline release preparation. Never publishes or creates keys.

Run on the exact checkout used to build the installer, with the official
WinSparkle 0.9.4 signing tool and an owner-controlled key OUTSIDE the checkout.
The output is a candidate appcast, not proof of a successful native update.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPARKLE = "http://www.andymatuschak.org/xml-namespaces/sparkle"
RELEASES = "https://github.com/moyashimisosoup/black-cut-auto-print/releases/download"
ET.register_namespace("sparkle", SPARKLE)


def identity():
    # Read constants without executing application code.
    def read(path, name):
        source = (ROOT / path).read_text(encoding="utf-8-sig")
        match = re.search(r'^' + name + r' = "([^"]+)"$', source, re.M)
        if not match:
            raise ValueError("Missing release identity: " + name)
        return match[1]
    return read("app/version_info.py", "APP_VERSION"), read(
        "app/update_identity.py", "BUILD_NUMBER")


def candidate_xml(version, build, previous_build, filename, size, signature):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9]+(?:\.[a-z0-9]+)*)?", version):
        raise ValueError("Invalid display version")
    if not re.fullmatch(r"[1-9][0-9]{0,8}", build):
        raise ValueError("Invalid build number")
    if not re.fullmatch(r"0|[1-9][0-9]{0,8}", previous_build) or int(build) <= int(previous_build):
        raise ValueError("Build number must increase")
    if filename != f"BlackCutPrint-Setup-{version}.exe" or size <= 0:
        raise ValueError("Incorrect installer filename or empty installer")
    if not re.fullmatch(r"[A-Za-z0-9+/]{86}==", signature) or len(
            base64.b64decode(signature, validate=True)) != 64:
        raise ValueError("Invalid EdDSA signature encoding")
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "APP-033 BlackCutPrint"
    ET.SubElement(channel, "description").text = "Managed Windows updates"
    ET.SubElement(channel, "language").text = "ja"
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = f"BlackCutPrint {version}"
    ET.SubElement(item, "enclosure", {
        "url": f"{RELEASES}/v{version}/{filename}",
        "length": str(size),
        "type": "application/octet-stream",
        f"{{{SPARKLE}}}version": build,
        f"{{{SPARKLE}}}shortVersionString": version,
        f"{{{SPARKLE}}}edSignature": signature,
        f"{{{SPARKLE}}}os": "windows-x64",
        f"{{{SPARKLE}}}installerArguments": "/SILENT /SP- /NORESTART",
    })
    ET.indent(rss)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True) + b"\n"


def fingerprint(path):
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Installer is not a Windows executable")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return path.stat().st_size, digest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installer", type=Path, required=True)
    p.add_argument("--tool", type=Path, required=True)
    p.add_argument("--private-key", type=Path, required=True)
    p.add_argument("--previous-build", required=True,
                   help="Last distributed build number; 0 only if none")
    p.add_argument("--output", type=Path, required=True,
                   help="New local appcast.xml file; never overwrites")
    args = p.parse_args(argv)
    try:
        version, build = identity()
        installer = args.installer.resolve(strict=True)
        tool = args.tool.resolve(strict=True)
        key = args.private_key.resolve(strict=True)
        if not key.is_file() or key.is_relative_to(ROOT):
            raise ValueError("Private key must be outside the repository")
        if not tool.is_file() or tool.name.lower() != "winsparkle-tool.exe":
            raise ValueError("Use the verified official signing executable")
        if args.output.name != "appcast.xml" or args.output.exists():
            raise ValueError("Output must be a new appcast.xml")
        size, digest = fingerprint(installer)
        # Fail on metadata errors BEFORE using the signing key.
        candidate_xml(version, build, args.previous_build, installer.name,
                      size, base64.b64encode(bytes(64)).decode("ascii"))
        proc = subprocess.run(
            [str(tool), "sign", "--private-key-file", str(key), str(installer)],
            capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0:
            raise ValueError("WinSparkle signing failed; inspect locally")
        signature = proc.stdout.strip()
        if fingerprint(installer) != (size, digest):
            raise ValueError("Installer changed during signing")
        xml = candidate_xml(version, build, args.previous_build,
                            installer.name, size, signature)
        with args.output.open("xb") as stream:
            stream.write(xml)
        print(f"Candidate only: v{version} / build {build}")
        print(f"Installer SHA256: {digest}")
        print("Verify native A-to-B and rejection cases before publishing.")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        # Never echo secret paths, command lines, or tool stderr.
        print("Release preparation failed. Check local inputs and version metadata.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
