"""Security policy, dependency updates, code scanning and the repository report card, and the rules they must follow."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
SECURITY_WORKFLOWS = {"codeql.yml", "scorecard.yml"}
ADVISORY_URL = "https://github.com/huytquocxx/ba-bpmn/security/advisories/new"


def read(path):
    return Path(path).read_text(encoding="utf-8")


def test_the_expected_workflows_exist():
    assert {w.name for w in WORKFLOWS} >= {"check.yml", "codeql.yml", "scorecard.yml"}


def test_every_workflow_pins_every_action_to_a_commit_and_avoids_risky_triggers():
    for workflow in WORKFLOWS:
        body = read(workflow)
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)(.*)$", body, re.M)
        assert uses, workflow.name
        for action, rest in uses:
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", action), f"{workflow.name}: {action} is not pinned"
            assert re.search(r"#\s*v\d+\.\d+\.\d+", rest), f"{workflow.name}: {action} needs its release in a comment"
        assert "pull_request_target" not in body, workflow.name
        assert "secrets." not in body, f"{workflow.name} should not need any secret"
        assert "github.event." not in body and "github.head_ref" not in body, f"{workflow.name}: untrusted text in a command"


def test_every_workflow_starts_with_read_only_permissions_and_only_security_ones_may_write():
    for workflow in WORKFLOWS:
        body = read(workflow)
        assert re.search(r"^permissions:\n  contents: read\n(?!  )", body, re.M) or re.search(
            r"^permissions: read-all$", body, re.M), f"{workflow.name}: the top-level permissions must be read-only"
        assert "write-all" not in body
        if workflow.name not in SECURITY_WORKFLOWS:
            assert ": write" not in body, f"{workflow.name} must not write anything"
    assert "id-token: write" not in read(ROOT / ".github/workflows/codeql.yml")


def test_codeql_scans_every_language_in_the_repository_on_a_schedule():
    body = read(ROOT / ".github/workflows/codeql.yml")
    for language in ("python", "javascript-typescript", "actions"):
        assert language in body, language
    assert re.search(r"^\s+- cron:", body, re.M), "it should also run on a schedule, not only on changes"
    assert re.search(r"push:\n\s+branches: \[main\]", body) and "pull_request:" in body
    assert "security-events: write" in body
    # init and analyze must come from the same pinned commit
    commits = set(re.findall(r"github/codeql-action/(?:init|analyze)@([0-9a-f]{40})", body))
    assert len(commits) == 1


def test_scorecard_runs_weekly_and_does_not_publish_the_score_yet():
    body = read(ROOT / ".github/workflows/scorecard.yml")
    assert re.search(r"^\s+- cron:", body, re.M) and "branch_protection_rule:" in body
    assert re.search(r"publish_results:\s*false", body), "publishing the score is the owner's decision"
    assert "upload-sarif" in body and "security-events: write" in body


def test_dependabot_watches_python_node_and_the_actions_weekly():
    body = read(ROOT / ".github" / "dependabot.yml")
    assert re.search(r"^version: 2$", body, re.M)
    blocks = re.split(r"\n  - package-ecosystem:", "\n" + body)[1:]
    seen = {}
    for block in blocks:
        name = block.split("\n", 1)[0].strip().strip('"')
        directory = re.search(r'directory:\s*"([^"]+)"', block).group(1)
        assert re.search(r"interval:\s*\"?weekly", block), f"{name} {directory} should be weekly"
        assert "open-pull-requests-limit:" in block
        seen.setdefault(name, set()).add(directory)
    assert seen == {"pip": {"/"}, "npm": {"/docs/diagrams"}, "github-actions": {"/"}}, seen


def test_dependabot_does_not_propose_mcp_version_2_while_the_server_needs_version_1():
    body = read(ROOT / ".github" / "dependabot.yml")
    pip_block = re.split(r"\n  - package-ecosystem:", "\n" + body)[1]
    assert re.search(r'dependency-name:\s*"mcp"\s*\n\s+versions:\s*\[">=2"\]', pip_block), "see docs/TRAPS.md, Trap 10"
    assert 'mcp>=1.2,<2' in read(ROOT / "pyproject.toml"), "lift the ignore rule only together with the pin"


def test_security_policy_tells_people_how_to_report_privately():
    policy = read(ROOT / "SECURITY.md")
    assert ADVISORY_URL in policy
    for needed in ("Supported versions", "What to include", "What to expect"):
        assert needed in policy, needed
    assert "@" not in policy, "no email address: reports go through GitHub's private form"
    assert "[SECURITY.md](SECURITY.md)" in read(ROOT / "README.md") or "(SECURITY.md)" in read(ROOT / "README.md")


def test_readme_has_a_security_section():
    readme = read(ROOT / "README.md")
    assert re.search(r"^## Security$", readme, re.M)
