"""Checks to run before anything is published.

    python scripts/prepublish.py                 run every check
    python scripts/prepublish.py --preview       also show the README the way GitHub will draw it (needs `gh auth login`)
    python scripts/prepublish.py --install-hook  make Git run the checks before every push (once per clone)
    python scripts/prepublish.py --hook          what the Git hook runs: every check, no preview

Checks: generated files in step, no "TBC" left, every link and image exists, the text rules, and the whole test suite
(which also scans for secrets, client names, personal paths and oversized files).
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"node_modules", ".git", "__pycache__", ".venv", "venv", "bpmn-output", ".pytest_cache"}
EM_DASH, EN_DASH = "\u2014", "\u2013"


# ---------------------------------------------------------------- text checks
def public_markdown(root=ROOT):
    """The pages a stranger reads."""
    root = Path(root)
    files = list(root.glob("*.md")) + [root / "src" / "bpmn_mcp" / "spec_format.md"]
    for pattern in ("docs/**/*.md", "plugins/**/*.md", "skills/**/*.md"):
        files += root.glob(pattern)
    return sorted({p for p in files if p.exists() and not (set(p.relative_to(root).parts) & SKIP)})


def _prose(text):
    """The text without fenced code blocks (kept as blank lines so line numbers stay right)."""
    return re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def broken_links(root=ROOT):
    """Relative links and images that point at a file that does not exist."""
    root, problems = Path(root), []
    for md in public_markdown(root):
        text = _prose(md.read_text(encoding="utf-8"))
        targets = re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'(?:src|srcset)="([^"]+)"', text)
        for target in targets:
            target = target.split("#")[0].split("?")[0]
            if not target or re.match(r"^(https?:|mailto:|/)", target):
                continue
            if not (md.parent / target).exists():
                problems.append(f"{md.relative_to(root).as_posix()}: {target} does not exist")
    return problems


def style_problems(root=ROOT):
    """Dashes the owner does not want, and accidentally repeated words."""
    root, problems = Path(root), []
    for md in public_markdown(root):
        rel = md.relative_to(root).as_posix()
        for number, line in enumerate(_prose(md.read_text(encoding="utf-8")).splitlines(), 1):
            line = re.sub(r"`[^`\n]*`", "", line)
            if EM_DASH in line or EN_DASH in line:
                problems.append(f"{rel}:{number}: a long dash; use a comma, a colon or a new sentence")
            repeated = re.search(r"\b([A-Za-z]{3,})\s+\1\b", line, re.I)
            if repeated:
                problems.append(f"{rel}:{number}: repeated word '{repeated.group(1)}'")
    return problems


# ---------------------------------------------------------------- the GitHub preview
def repo_slug(root=ROOT):
    import json
    repository = json.loads((Path(root) / "packaging.json").read_text(encoding="utf-8"))["repository"]
    return re.search(r"github\.com/([^/]+/[^/.]+)", repository).group(1)


def render_with_github(root, slug):
    """The README as GitHub's own renderer draws it (uses the gh sign-in; nothing is published)."""
    gh = shutil.which("gh") or next((p for p in (r"C:\Program Files\GitHub CLI\gh.exe",) if Path(p).exists()), None)
    if not gh:
        raise RuntimeError("the GitHub command line (gh) is not installed")
    done = subprocess.run([gh, "api", "markdown", "-H", "Accept: text/html", "-f", "mode=gfm", "-f", f"context={slug}",
                           "-F", "text=@README.md"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        raise RuntimeError(f"GitHub did not render the README: {done.stderr.strip()[:200]}")
    return done.stdout


def preview(root=ROOT, out_dir=None, renderer=render_with_github):
    """Write README-preview.html, with local images, and report anything GitHub dropped. Returns (page, problems)."""
    root = Path(root).resolve()
    html = renderer(root, repo_slug(root))
    # tags written inside code are shown as text by GitHub, so only count the ones outside code
    source = re.sub(r"`[^`\n]*`", "", _prose((root / "README.md").read_text(encoding="utf-8")))
    problems = []
    for tag in ("<picture", "<source", "<img"):
        if source.count(tag) != html.count(tag):
            problems.append(f"GitHub kept {html.count(tag)} of {source.count(tag)} {tag}> tags from the README")
    out = Path(out_dir) if out_dir else Path(tempfile.gettempdir()) / "ba-bpmn-preview"
    out.mkdir(parents=True, exist_ok=True)
    page = out / "README-preview.html"
    page.write_text(
        f'<!doctype html><meta charset="utf-8"><base href="{root.as_uri()}/">'
        '<style>body{font:16px/1.5 -apple-system,"Segoe UI",Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;'
        'color:#1f2328}table{border-collapse:collapse}td,th{border:1px solid #d0d7de;padding:6px 13px}'
        'code{background:#eff1f3;padding:.2em .4em;border-radius:6px}pre{background:#f6f8fa;padding:16px;overflow:auto}'
        'img{max-width:100%}blockquote{border-left:4px solid #d0d7de;margin:0;padding:0 1em;color:#59636e}</style>'
        f'<article>{html}</article>', encoding="utf-8")
    return page, problems


# ---------------------------------------------------------------- the hook
def install_hook(root=ROOT):
    subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=root, check=True)
    print("Git will now run the pre-publish checks before every push in this clone.")
    print("To push once without them: git push --no-verify")


# ---------------------------------------------------------------- running everything
def run_checks(root=ROOT, with_tests=True):
    """[(title, [problems])]"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sync_plugins
    results = [("generated files match their sources", sync_plugins.drift()),
               ("no placeholders left", sync_plugins.release_problems()),
               ("every link and image exists", broken_links(root)),
               ("text rules (no long dashes, no repeated words)", style_problems(root))]
    if with_tests:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
                              cwd=root, capture_output=True, text=True, encoding="utf-8")
        tail = (done.stdout + done.stderr).strip().splitlines()[-12:]
        if done.returncode and "No module named pytest" in done.stdout + done.stderr:
            tail = ['pytest is not installed for this Python. Run: pip install -e ".[test]"']
        results.append(("the test suite (includes the secret, client-name and file-size scans)",
                        tail if done.returncode else []))
    return results


def main(argv):
    if "--install-hook" in argv:
        install_hook()
        return 0
    failed = 0
    for title, problems in run_checks(with_tests="--no-tests" not in argv):
        print(f"{'FAIL' if problems else 'PASS'}  {title}")
        for line in problems:
            print(f"        {line}")
        failed += bool(problems)
    if "--preview" in argv:
        try:
            page, problems = preview()
        except RuntimeError as error:
            print(f"FAIL  preview: {error}")
            failed += 1
        else:
            print(f"{'FAIL' if problems else 'PASS'}  GitHub keeps everything in the README")
            for line in problems:
                print(f"        {line}")
            failed += bool(problems)
            print(f"      Open this file to see it: {page}")
    if failed:
        print(f"\n{failed} check(s) failed. Fix them" + (", or push anyway with: git push --no-verify" if "--hook" in argv else "."))
    else:
        print("\nAll checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
