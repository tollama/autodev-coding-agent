"""Tests for autodev.template_registry module."""

from __future__ import annotations

import json
import os

from autodev.template_registry import TemplateManifest, TemplateRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_template(tmp_path, name: str, manifest: dict | None = None) -> None:
    """Create a template directory with optional manifest.json."""
    tpl_dir = os.path.join(str(tmp_path), name)
    os.makedirs(tpl_dir, exist_ok=True)
    if manifest is not None:
        with open(os.path.join(tpl_dir, "manifest.json"), "w") as f:
            json.dump(manifest, f)


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


def test_discovers_directories(tmp_path):
    """Should discover template directories."""
    _create_template(tmp_path, "python_fastapi")
    _create_template(tmp_path, "python_cli")

    reg = TemplateRegistry(str(tmp_path))
    names = reg.list_templates()
    assert "python_fastapi" in names
    assert "python_cli" in names


def test_loads_manifest_json(tmp_path):
    """Should load manifest.json when present."""
    _create_template(tmp_path, "custom", {
        "language": "go",
        "runtime": "go1.21",
        "validators": ["golint"],
        "test_command": "go test ./...",
    })

    reg = TemplateRegistry(str(tmp_path))
    m = reg.get("custom")
    assert m is not None
    assert m.language == "go"
    assert m.runtime == "go1.21"
    assert "golint" in m.validators
    assert m.test_command == "go test ./..."


def test_python_default_for_missing_manifest(tmp_path):
    """Templates without manifest should get Python defaults."""
    _create_template(tmp_path, "legacy_template")

    reg = TemplateRegistry(str(tmp_path))
    m = reg.get("legacy_template")
    assert m is not None
    assert m.language == "python"
    assert m.runtime == "cpython"
    assert "ruff" in m.validators


def test_skips_dot_and_underscore_dirs(tmp_path):
    """Directories starting with . or _ should be skipped."""
    _create_template(tmp_path, ".hidden")
    _create_template(tmp_path, "_private")
    _create_template(tmp_path, "visible")

    reg = TemplateRegistry(str(tmp_path))
    names = reg.list_templates()
    assert ".hidden" not in names
    assert "_private" not in names
    assert "visible" in names


def test_skips_files_not_dirs(tmp_path):
    """Regular files in template root should be ignored."""
    with open(os.path.join(str(tmp_path), "readme.txt"), "w") as f:
        f.write("not a template")
    _create_template(tmp_path, "real_template")

    reg = TemplateRegistry(str(tmp_path))
    assert reg.list_templates() == ["real_template"]


def test_list_templates_sorted(tmp_path):
    """Template names should be returned in sorted order."""
    _create_template(tmp_path, "z_template")
    _create_template(tmp_path, "a_template")
    _create_template(tmp_path, "m_template")

    reg = TemplateRegistry(str(tmp_path))
    names = reg.list_templates()
    assert names == sorted(names)


def test_get_returns_none_for_unknown(tmp_path):
    """get() should return None for unknown template."""
    reg = TemplateRegistry(str(tmp_path))
    assert reg.get("nonexistent") is None


def test_exists_returns_correct_boolean(tmp_path):
    """exists() should correctly check template presence."""
    _create_template(tmp_path, "present")
    reg = TemplateRegistry(str(tmp_path))
    assert reg.exists("present") is True
    assert reg.exists("absent") is False


def test_handles_nonexistent_root():
    """Nonexistent root directory should produce empty registry."""
    reg = TemplateRegistry("/nonexistent/template/root")
    assert reg.list_templates() == []


def test_template_manifest_from_dict_defaults():
    """from_dict should fill defaults for missing fields."""
    m = TemplateManifest.from_dict("test", {})
    assert m.name == "test"
    assert m.language == "python"
    assert m.runtime == "cpython"
    assert m.scaffold_files == []
    assert m.test_command == ""
