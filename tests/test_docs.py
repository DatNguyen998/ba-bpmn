"""The instruction files, the traps list and the public-repository rules."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_FILES = {"bpmn-viewer.development.js", "test_docs.py"}      # third-party file; this file names the banned terms


def candidate_files():
    """The files that would be published: everything Git would add, so ignored build output is left out."""
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                             capture_output=True, text=True, check=True, encoding="utf-8").stdout
        return [ROOT / line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in ROOT.rglob("*") if p.is_file()]


def text_files():
    for path in candidate_files():
        if path.is_file() and not (set(path.parts) & SKIP_DIRS) and path.name not in SKIP_FILES \
                and path.suffix in {".md", ".py", ".json", ".toml", ".txt", ""}:
            yield path


def test_claude_md_only_imports_agents_md():
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"


def test_agents_md_stays_short():
    lines = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    assert 10 < len(lines) <= 120, "keep the instruction file short (Anthropic suggests well under 200 lines)"


def test_agents_md_points_at_the_traps_list_and_the_sync_script():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/TRAPS.md" in text and "scripts/sync_plugins.py" in text


def test_files_named_in_agents_md_exist():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    names = set(re.findall(r"`([\w./-]+\.(?:md|py|json|js|toml))`", text))
    assert names, "expected the file to name some files"
    for name in names:
        if "/" in name:
            assert (ROOT / name).exists(), name
        else:
            assert any(p.name == name for p in ROOT.rglob(name) if not (set(p.parts) & SKIP_DIRS)), name


def test_traps_are_numbered_without_gaps_and_complete():
    text = (ROOT / "docs" / "TRAPS.md").read_text(encoding="utf-8")
    numbers = [int(n) for n in re.findall(r"^## Trap (\d+):", text, re.M)]
    assert numbers == list(range(1, len(numbers) + 1)) and numbers
    for block in re.split(r"^## Trap \d+:.*$", text, flags=re.M)[1:]:
        for field in ("**Symptom:**", "**Cause:**", "**Fix lives in:**", "**Status:**"):
            assert field in block, field


def test_no_client_or_personal_terms_in_the_public_repository():
    banned = re.compile("|".join(["CI" + "MB", "DS" + "ME", "sme" + "-flow", "flexi" + "pay", "net" + "reveal",
                                  "red" + "E2e", "Bit" + "bucket", r"C:\\Users\\", r"/Users/\w"]), re.I)
    for path in text_files():
        hit = banned.search(path.read_text(encoding="utf-8", errors="ignore"))
        assert not hit, f"{path.relative_to(ROOT)}: {hit.group(0)}"


def test_no_secret_shaped_strings():
    secret = re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY")
    for path in text_files():
        assert not secret.search(path.read_text(encoding="utf-8", errors="ignore")), path.name
