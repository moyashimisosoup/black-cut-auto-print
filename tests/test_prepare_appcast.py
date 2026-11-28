"""Metadata tests only; no real key, signing tool, network or execution."""
import base64
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

spec = importlib.util.spec_from_file_location(
    "app033_prepare_appcast",
    Path(__file__).resolve().parents[1] / "packaging" / "prepare_appcast.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SIG = base64.b64encode(bytes(range(64))).decode("ascii")


def metadata(**overrides):
    args = dict(version="0.7.4-rc.1", build="70401", previous_build="70301",
                filename="BlackCutPrint-Setup-0.7.4-rc.1.exe", size=123, signature=SIG)
    args.update(overrides)
    return module.candidate_xml(**args)


def test_exact_version_asset_and_signed_enclosure():
    enclosure = ET.fromstring(metadata()).find("./channel/item/enclosure")
    assert enclosure.attrib["url"] == (
        module.RELEASES + "/v0.7.4-rc.1/BlackCutPrint-Setup-0.7.4-rc.1.exe")
    assert enclosure.attrib["length"] == "123"
    ns = "{" + module.SPARKLE + "}"
    assert enclosure.attrib[ns + "version"] == "70401"
    assert enclosure.attrib[ns + "shortVersionString"] == "0.7.4-rc.1"
    assert enclosure.attrib[ns + "edSignature"] == SIG
    assert enclosure.attrib[ns + "os"] == "windows-x64"
    assert "/NORESTART" in enclosure.attrib[ns + "installerArguments"]


@pytest.mark.parametrize("overrides", [
    {"build": "70301"}, {"build": "70300"}, {"build": "0"}, {"build": "070401"},
    {"previous_build": "-1"}, {"previous_build": "not-a-number"},
    {"version": "../update-feed"}, {"filename": "BlackCutPrint.exe"},
    {"size": 0}, {"signature": ""}, {"signature": "not-base64"},
    {"signature": base64.b64encode(bytes(32)).decode("ascii")},
])
def test_bad_metadata_rejected(overrides):
    with pytest.raises(ValueError):
        metadata(**overrides)


def test_fingerprint_detects_mutation(tmp_path):
    path = tmp_path / "setup.exe"
    path.write_bytes(b"MZfirst")
    initial = module.fingerprint(path)
    path.write_bytes(b"MZother")
    assert module.fingerprint(path) != initial
    path.write_bytes(b"not an exe")
    with pytest.raises(ValueError):
        module.fingerprint(path)


@pytest.mark.parametrize("verify_result", [0, 1])
def test_feed_requires_official_verification(tmp_path, monkeypatch, verify_result):
    from types import SimpleNamespace

    installer = tmp_path / "BlackCutPrint-Setup-0.7.4-rc.1.exe"
    installer.write_bytes(b"MZfake")
    tool = tmp_path / "winsparkle-tool.exe"
    tool.touch()
    key = tmp_path / "test.key"
    key.touch()
    output = tmp_path / "appcast.xml"
    public_key = base64.b64encode(bytes(range(32))).decode("ascii")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "sign":
            return SimpleNamespace(returncode=0, stdout=SIG)
        assert argv[1:] == ["verify", "--public-key", public_key,
                            "--signature", SIG, str(installer)]
        return SimpleNamespace(returncode=verify_result, stdout="")

    monkeypatch.setattr(module, "identity", lambda: ("0.7.4-rc.1", "70401"))
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.main(["--installer", str(installer), "--tool", str(tool),
                          "--private-key", str(key), "--public-key", public_key,
                          "--previous-build", "70301", "--output", str(output)])
    assert len(calls) == 2
    assert result == verify_result
    assert output.exists() == (verify_result == 0)
