import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_STORED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGER = ROOT / "tools/package_delivery_beta.py"
CHECKER = ROOT / "skills/method/bmad-deliver/scripts/check_install.py"


def load_script(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def builder(monkeypatch):
    package = load_script(PACKAGER)
    monkeypatch.setattr(package, "historical_brief_file", lambda name: ("test Product Brief " + name).encode())
    return package


def pack(builder, monkeypatch, archive, *options):
    monkeypatch.setattr(sys, "argv", [str(PACKAGER), str(archive), *map(str, options)])
    builder.main()


def check(script, skill):
    return subprocess.run([sys.executable, "-B", str(script), str(skill)], capture_output=True, text=True, timeout=10)


def test_matching_input_manifest_reproduces_the_archive(builder, monkeypatch, tmp_path):
    original = tmp_path / "original.zip"
    rebuilt = tmp_path / "rebuilt.zip"
    unpacked = tmp_path / "unpacked"
    pack(builder, monkeypatch, original)
    with ZipFile(original) as archive:
        manifest = json.loads(archive.read(builder.SOURCE_MANIFEST))
        members = set(archive.namelist())
        assert manifest["product_brief_revision"] == builder.BRIEF_REVISION
        assert manifest["archive_format"] == "zip-stored-v1"
        assert manifest["builder_sha256"] == hashlib.sha256(PACKAGER.read_bytes()).hexdigest()
        assert manifest["worktree_sources"]["bmad-deliver/scripts/deliver.py"] == (
            "skills/method/bmad-deliver/scripts/deliver.py"
        )
        assert set(manifest["files"]) == members - {builder.SOURCE_MANIFEST, "SHA256SUMS"}
        assert set(manifest["files"]) == {"INSTALL.md", *manifest["worktree_sources"], *manifest["historical_sources"]}
        for name, expected in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
            assert archive.getinfo(name).compress_type == ZIP_STORED
        checksums = {
            name: digest
            for digest, name in (line.split("  ", 1) for line in archive.read("SHA256SUMS").decode().splitlines())
        }
        assert set(checksums) == members - {"SHA256SUMS"}
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == digest for name, digest in checksums.items())
        archive.extractall(unpacked)
    inputs = unpacked / builder.SOURCE_MANIFEST
    pack(builder, monkeypatch, rebuilt, "--inputs", inputs)
    assert original.read_bytes() == rebuilt.read_bytes()

    with pytest.raises(SystemExit) as exists:
        pack(builder, monkeypatch, original)
    assert exists.value.code == 1
    assert original.read_bytes() == rebuilt.read_bytes()
    inputs.write_text("{}")
    different = tmp_path / "different.zip"
    with pytest.raises(SystemExit) as mismatch:
        pack(builder, monkeypatch, different, "--inputs", inputs)
    assert mismatch.value.code == 1
    assert not different.exists()


def test_missing_historical_object_leaves_no_archive(monkeypatch, tmp_path, capsys):
    package = load_script(PACKAGER)
    monkeypatch.setattr(package, "BRIEF_REVISION", "0" * 40)
    archive = tmp_path / "missing.zip"
    with pytest.raises(SystemExit) as error:
        pack(package, monkeypatch, archive)
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert "Cannot read Product Brief input" in message and "checkout with the pinned commit" in message
    assert not archive.exists()


def test_checker_keeps_a_legacy_install_available_and_detects_candidate_damage(builder, monkeypatch, tmp_path):
    legacy = tmp_path / "previous/.agents/skills/bmad-deliver"
    legacy_manifest = legacy / "assets/native/SOURCE.json"
    legacy_manifest.parent.mkdir(parents=True)
    legacy_manifest.write_text('{"checkout_head":"historical"}')
    saved = legacy_manifest.read_bytes()

    archive = tmp_path / "candidate.zip"
    pack(builder, monkeypatch, archive)
    new = tmp_path / "candidate/.agents/skills"
    with ZipFile(archive) as package:
        package.extractall(new)
    candidate = new / "bmad-deliver"
    checker = candidate / "scripts/check_install.py"
    valid = check(checker, candidate)
    assert valid.returncode == 0 and "Compatible beta install" in valid.stdout
    old = check(checker, legacy)
    assert old.returncode == 1 and "Legacy beta install" in old.stderr
    assert legacy_manifest.read_bytes() == saved

    (candidate / "scripts/run_metrics.py").write_text("unexpected edit")
    damaged = check(checker, candidate)
    assert damaged.returncode == 1 and "Checksum mismatch for scripts/run_metrics.py" in damaged.stderr
    (candidate / "scripts/run_metrics.py").unlink()
    missing = check(checker, candidate)
    assert missing.returncode == 1 and "Missing or redirected installed file scripts/run_metrics.py" in missing.stderr
    missing_runtime = "assets/native/runtime/memlog.py"
    manifest_path = candidate / "assets/native/SOURCE.json"
    broken = json.loads(manifest_path.read_text())
    del broken["files"][f"bmad-deliver/{missing_runtime}"]
    (candidate / missing_runtime).unlink()
    manifest_path.write_text(json.dumps(broken))
    incomplete = check(checker, candidate)
    assert incomplete.returncode == 1 and "required runtime inventory" in incomplete.stderr


def test_compatibility_check_detects_unsupported_host_and_missing_optional_commands(monkeypatch):
    checker = load_script(CHECKER)
    monkeypatch.setattr(checker, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(checker, "sys", SimpleNamespace(version_info=(3, 10)))
    monkeypatch.setattr(checker.shutil, "which", lambda command: None)
    assert checker.platform_issues(native=True, codex=True) == [
        "Python 3.11 or later is required.",
        "A POSIX host is required.",
        "Install uv on PATH for native delivery.",
        "Install codex on PATH for the standard launcher.",
    ]
