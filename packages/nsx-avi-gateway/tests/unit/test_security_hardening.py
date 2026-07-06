"""Security hardening regression tests."""

from pathlib import Path


def test_no_hardcoded_default_password_string_in_source():
    """The repository should not contain the old default credential value."""
    repo_root = Path(__file__).resolve().parents[2]
    file_extensions = {".py", ".md", ".toml", ".yml", ".yaml", ".example"}
    ignored_dirs = {".git", ".venv", ".mypy_cache", ".pytest_cache", "htmlcov"}
    password = "".join(map(chr, [112, 97, 115, 115, 119, 111, 114, 100]))
    risky_snippets = [
        f'= "{password}"',
        f"= '{password}'",
        f': "{password}"',
        f": '{password}'",
        f"&{password}={password}",
        f"| {password} |",
    ]

    offenders: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix not in file_extensions:
            continue
        if any(part in ignored_dirs for part in path.parts):
            continue
        if path.name == "test_security_hardening.py":
            continue

        text = path.read_text(encoding="utf-8")
        if any(snippet in text for snippet in risky_snippets):
            offenders.append(str(path.relative_to(repo_root)))

    assert offenders == []
