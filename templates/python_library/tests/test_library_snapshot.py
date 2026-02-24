from pathlib import Path


def test_library_template_has_required_quality_artifacts():
    root = Path(__file__).resolve().parents[1]
    for rel in [
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "README.md",
        ".semgrep.yml",
        "scripts/generate_sbom.py",
        "contracts/library_contract.json",
        ".github/workflows/ci.yml",
    ]:
        assert (root / rel).exists(), f"Missing template file: {rel}"

    content = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.ruff]" in content
    assert "[tool.mypy]" in content
