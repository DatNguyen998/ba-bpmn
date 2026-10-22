"""The GitHub workflow that runs the checks: least privilege, pinned actions, and the claims it makes are the ones tested."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"


def text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_exists_and_runs_on_pushes_to_main_and_on_pull_requests():
    body = text()
    assert re.search(r"^on:\n(?:.*\n)*?\s+push:\n\s+branches: \[main\]", body, re.M)
    assert re.search(r"^\s+pull_request:", body, re.M)
    assert "pull_request_target" not in body, "that trigger gives pull requests from forks access to secrets"


def test_workflow_has_only_read_access():
    body = text()
    assert re.search(r"^permissions:\n  contents: read\n(?!  )", body, re.M), "grant read access to contents and nothing else"
    assert "secrets." not in body


def test_every_action_is_pinned_to_a_commit_with_its_version_in_a_comment():
    uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)(.*)$", text(), re.M)
    assert uses, "expected at least checkout and setup-python"
    for action, rest in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), f"{action} is not pinned to a full commit"
        assert re.search(r"#\s*v\d+\.\d+\.\d+", rest), f"{action}: say which release the commit is"


def test_checkout_does_not_keep_the_token():
    assert "persist-credentials: false" in text()


def test_workflow_does_not_put_untrusted_event_text_into_commands():
    assert "github.event." not in text() and "github.head_ref" not in text()


def test_matrix_covers_linux_windows_and_the_oldest_python_the_project_claims():
    body = text()
    assert "ubuntu-latest" in body and "windows-latest" in body
    floor = re.search(r'requires-python\s*=\s*">=(\d+\.\d+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8")).group(1)
    assert f'"{floor}"' in body, f"the lowest supported Python ({floor}) must be in the matrix, or the claim is untested"
    assert "fail-fast: false" in body, "one failing combination must not hide the others"
    assert "timeout-minutes:" in body


def test_workflow_runs_the_same_checks_as_the_local_gate():
    body = text()
    assert "scripts/prepublish.py --no-tests" in body
    assert "--cov-fail-under=80" in body, "the project holds 80% coverage on its own code"
    assert 'pip install -e ".[test]"' in body


def test_linux_browser_gets_the_flag_it_needs_only_on_linux():
    # job-level settings can read the matrix but not the runner (GitHub rejects `runner.os` there)
    assert re.search(r"BPMN_BROWSER_ARGS:.*matrix\.os == 'ubuntu-latest'.*--no-sandbox", text())
    assert "runner.os" not in text()
