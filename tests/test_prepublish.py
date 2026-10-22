"""The checks that run before anything is published (scripts/prepublish.py) and the Git hook that runs them."""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("prepublish", ROOT / "scripts" / "prepublish.py")
pp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pp)

EM, EN = "—", "–"      # written as escapes so this file stays free of the characters it tests for


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_broken_links_finds_missing_targets_but_not_web_links_or_anchors(tmp_path):
    write(tmp_path, "README.md",
          "[ok](docs/a.md) [web](https://example.com/x) [anchor](#top) [bad](docs/missing.md)\n"
          '<picture><source srcset="img/dark.svg"><img alt="x" src="img/gone.svg"></picture>\n')
    write(tmp_path, "docs/a.md", "fine\n")
    found = " ".join(pp.broken_links(tmp_path))
    assert "docs/missing.md" in found and "img/dark.svg" in found and "img/gone.svg" in found
    assert "docs/a.md" not in found and "example.com" not in found and "#top" not in found


def test_broken_links_ignores_examples_inside_code_blocks(tmp_path):
    write(tmp_path, "README.md", "```\n[not a link](nowhere.md)\n```\n")
    assert pp.broken_links(tmp_path) == []


def test_style_flags_dashes_and_repeated_words_but_not_code(tmp_path):
    write(tmp_path, "README.md",
          f"This line is fine.\nA bad {EM} dash and the the repeat.\nA range 1{EN}2.\n"
          f"```\ncode {EM} the the\n```\nInline `code {EM} here` is fine too.\n")
    problems = pp.style_problems(tmp_path)
    assert len(problems) == 3, problems
    assert all(p.startswith("README.md:") for p in problems)
    assert any(":2:" in p for p in problems) and any(":3:" in p for p in problems)


def test_the_real_repository_passes_the_text_checks():
    assert pp.broken_links(ROOT) == []
    assert pp.style_problems(ROOT) == []


def test_public_markdown_covers_the_pages_strangers_read():
    names = {p.relative_to(ROOT).as_posix() for p in pp.public_markdown(ROOT)}
    assert {"README.md", "AGENTS.md", "docs/TRAPS.md", "plugins/antigravity/README.md",
            "plugins/codex/ba-bpmn/README.md", "skills/bpmn-for-ba/SKILL.md"} <= names
    assert not any("node_modules" in n for n in names)


def test_repository_slug_comes_from_packaging_json():
    assert pp.repo_slug(ROOT) == "huytquocxx/ba-bpmn"


def test_preview_page_shows_local_images_and_reports_what_github_kept(tmp_path):
    write(tmp_path, "README.md", '<picture><source srcset="a.svg"><img alt="x" src="b.svg"></picture>\n')
    write(tmp_path, "packaging.json", '{"repository": "https://github.com/o/r.git", "server_command": "x"}')
    kept = '<h1>Hi</h1><picture><source srcset="a.svg"><img alt="x" src="b.svg"></picture>'
    page, problems = pp.preview(tmp_path, tmp_path / "out", renderer=lambda root, slug: kept)
    text = page.read_text(encoding="utf-8")
    assert "<base href=\"file:///" in text and kept in text and problems == []
    _, problems = pp.preview(tmp_path, tmp_path / "out2", renderer=lambda root, slug: "<h1>Hi</h1>")
    assert any("picture" in p for p in problems), "GitHub dropping the picture element must be reported"


def test_preview_does_not_count_tags_that_are_only_shown_as_code(tmp_path):
    """The README says `uvx --from <source>` in a code snippet; GitHub shows that as text, not as a tag."""
    write(tmp_path, "README.md", "Run `uvx --from <source> x`.\n\n```\n<picture><img src=\"z\"></picture>\n```\n"
                                 '<picture><source srcset="a.svg"><img alt="x" src="b.svg"></picture>\n')
    write(tmp_path, "packaging.json", '{"repository": "https://github.com/o/r.git", "server_command": "x"}')
    kept = '<p>Run <code>uvx --from &lt;source&gt; x</code>.</p><pre>&lt;picture&gt;</pre>' \
           '<picture><source srcset="a.svg"><img alt="x" src="b.svg"></picture>'
    _, problems = pp.preview(tmp_path, tmp_path / "out", renderer=lambda root, slug: kept)
    assert problems == []


def test_hook_runs_the_checks_and_says_how_to_skip():
    hook = (ROOT / ".githooks" / "pre-push").read_bytes().decode("utf-8")
    assert hook.startswith("#!/bin/sh")
    assert "scripts/prepublish.py --hook" in hook and "--no-verify" in hook
    assert "\r" not in hook, "shell scripts must keep Unix line endings"


def test_install_hook_points_git_at_the_hooks_folder(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    pp.install_hook(tmp_path)
    got = subprocess.run(["git", "config", "core.hooksPath"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert got.strip() == ".githooks"
