import pytest
from unittest.mock import MagicMock, patch
from autofix.agents.verifier import Verifier
from autofix.sandbox.docker_runner import DockerSandbox, ExecResult


def make_mock_sandbox(suite_passes: bool = True, dep_diff_lines: int = 0) -> MagicMock:
    sandbox = MagicMock(spec=DockerSandbox)
    sandbox.exec.side_effect = lambda cmd, **kw: (
        ExecResult(stdout="", stderr="", returncode=0)
        if ("pytest" in cmd and suite_passes) or ("pytest" not in cmd and dep_diff_lines == 0)
        else ExecResult(stdout=f"{dep_diff_lines}", stderr="", returncode=1 if "pytest" in cmd else 0)
    )
    return sandbox


def test_all_checks_pass():
    sandbox = make_mock_sandbox(suite_passes=True, dep_diff_lines=0)
    sandbox.exec.return_value = ExecResult(stdout="0", stderr="", returncode=0)

    verifier = Verifier(max_diff_lines=50, max_files_changed=3)
    # Override suite check to pass
    call_count = [0]
    def side_effect(cmd, **kw):
        call_count[0] += 1
        if "pytest" in cmd:
            return ExecResult(stdout="5 passed", stderr="", returncode=0)
        return ExecResult(stdout="0", stderr="", returncode=0)
    sandbox.exec.side_effect = side_effect

    result = verifier.verify(
        sandbox=sandbox,
        test_file_path="tests/test_regression_abc.py",
        patched_files=["app/routes.py"],
        diff_lines=5,
        test_failed_before=True,
    )
    assert result.passed
    assert result.checks["regression_test_failed_before_patch"] is True


def test_fails_when_test_did_not_fail_before():
    sandbox = MagicMock(spec=DockerSandbox)
    sandbox.exec.return_value = ExecResult(stdout="0", stderr="", returncode=0)

    verifier = Verifier()
    result = verifier.verify(
        sandbox=sandbox,
        test_file_path="tests/test_regression_abc.py",
        patched_files=["app/routes.py"],
        diff_lines=3,
        test_failed_before=False,  # Test passed before — invalid reproduction
    )
    assert not result.passed
    assert result.checks["regression_test_failed_before_patch"] is False


def test_fails_when_diff_too_large():
    sandbox = MagicMock(spec=DockerSandbox)
    sandbox.exec.return_value = ExecResult(stdout="0", stderr="", returncode=0)

    verifier = Verifier(max_diff_lines=50)
    result = verifier.verify(
        sandbox=sandbox,
        test_file_path="tests/test_regression_abc.py",
        patched_files=["app/routes.py"],
        diff_lines=100,  # over limit
        test_failed_before=True,
    )
    assert not result.passed
    assert result.checks["diff_within_50_lines"] is False


def test_fails_when_protected_path_touched():
    sandbox = MagicMock(spec=DockerSandbox)
    sandbox.exec.return_value = ExecResult(stdout="0", stderr="", returncode=0)

    verifier = Verifier()
    result = verifier.verify(
        sandbox=sandbox,
        test_file_path="tests/test_regression_abc.py",
        patched_files=[".github/workflows/ci.yml"],  # protected!
        diff_lines=5,
        test_failed_before=True,
    )
    assert not result.passed
    assert result.checks["no_protected_paths_touched"] is False


def test_fails_when_too_many_files_changed():
    sandbox = MagicMock(spec=DockerSandbox)
    sandbox.exec.return_value = ExecResult(stdout="0", stderr="", returncode=0)

    verifier = Verifier(max_files_changed=3)
    result = verifier.verify(
        sandbox=sandbox,
        test_file_path="tests/test_regression_abc.py",
        patched_files=["a.py", "b.py", "c.py", "d.py"],  # 4 files > limit 3
        diff_lines=10,
        test_failed_before=True,
    )
    assert not result.passed
    assert result.checks["files_changed_within_3"] is False
