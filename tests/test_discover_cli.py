# tests/test_discover_cli.py
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from connectors.cisco.models import Credential, DeviceFacts, NeighborLink
from crawler.crawl import CrawlResult
import discover


def test_prompt_credential_reads_username_and_masked_password():
    with patch("discover.input", return_value="admin", create=True), \
         patch("discover.getpass.getpass", return_value="secret"):
        cred = discover.prompt_credential()
    assert cred == Credential(username="admin", password="secret")


def test_confirm_returns_true_for_y():
    with patch("discover.input", return_value="y", create=True):
        assert discover.confirm("proceed?") is True


def test_confirm_returns_false_for_n():
    with patch("discover.input", return_value="n", create=True):
        assert discover.confirm("proceed?") is False


@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_happy_path_writes_and_commits_when_confirmed(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_reconcile, mock_derive_interfaces, mock_format_summary, mock_write_json, mock_git_commit,
):
    mock_prompt_cred.return_value = Credential(username="admin", password="secret")
    empty_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.return_value = empty_result
    mock_reconcile.return_value = []
    mock_confirm.return_value = True
    mock_write_json.return_value = MagicMock()

    rc = discover.main(["--seed", "10.0.0.1"])

    assert rc == 0
    mock_crawl.assert_called_once()
    mock_write_json.assert_called_once()
    mock_git_commit.assert_called_once()


@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_skips_write_when_user_declines(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_reconcile, mock_derive_interfaces, mock_format_summary, mock_write_json, mock_git_commit,
):
    mock_prompt_cred.return_value = Credential(username="admin", password="secret")
    empty_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.return_value = empty_result
    mock_reconcile.return_value = []
    mock_confirm.return_value = False

    rc = discover.main(["--seed", "10.0.0.1"])

    assert rc == 0
    mock_write_json.assert_not_called()
    mock_git_commit.assert_not_called()


@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_retries_auth_failed_devices_when_confirmed(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_reconcile, mock_derive_interfaces, mock_format_summary, mock_write_json, mock_git_commit,
):
    cred1 = Credential(username="admin", password="secret")
    cred2 = Credential(username="admin2", password="secret2")
    mock_prompt_cred.side_effect = [cred1, cred2]

    first_result = CrawlResult(visited={}, links=[], auth_failed=[("10.0.0.5", 1)], unreachable=[])
    second_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.side_effect = [first_result, second_result]
    mock_reconcile.return_value = []
    # 1st confirm() = "try alternate credentials?" -> True; 2nd confirm() = "write to file?" -> False
    mock_confirm.side_effect = [True, False]

    rc = discover.main(["--seed", "10.0.0.1"])

    assert rc == 0
    assert mock_crawl.call_count == 2
    second_call_kwargs = mock_crawl.call_args_list[1].kwargs
    # Full accumulated set: devices newly discovered during the retry have
    # never been offered cred1 and may need it.
    assert second_call_kwargs["credential_sets"] == [cred1, cred2]


@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.derive_interfaces", return_value=[])
@patch("discover.reconcile_links")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_retry_carries_forward_per_host_credential_rejections(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_reconcile, mock_derive_interfaces, mock_format_summary, mock_write_json, mock_git_commit,
):
    # The retry's seeds are exactly the devices that already refused cred1.
    # Without carrying the rejection map forward, resolve_device would re-submit
    # cred1 to every one of them (RESTCONF *and* SSH) before trying cred2 —
    # the same-credential retry the AAA-lockout constraint forbids.
    cred1 = Credential(username="admin", password="secret")
    cred2 = Credential(username="admin2", password="secret2")
    mock_prompt_cred.side_effect = [cred1, cred2]

    first_result = CrawlResult(
        visited={}, links=[], auth_failed=[("10.0.0.5", 1)], unreachable=[],
        rejected_credentials={"10.0.0.5": {"admin"}},
    )
    second_result = CrawlResult(visited={}, links=[], auth_failed=[], unreachable=[])
    mock_crawl.side_effect = [first_result, second_result]
    mock_reconcile.return_value = []
    mock_confirm.side_effect = [True, False]

    discover.main(["--seed", "10.0.0.1"])

    second_call_kwargs = mock_crawl.call_args_list[1].kwargs
    assert second_call_kwargs["rejected_credentials"] == {"10.0.0.5": {"admin"}}


@patch("discover.git_commit")
@patch("discover.write_json")
@patch("discover.format_summary", return_value="summary")
@patch("discover.apply_normalization")
@patch("discover.crawl")
@patch("discover.confirm")
@patch("discover.prompt_credential")
def test_main_derives_interfaces_for_both_ends_of_a_cable_seen_from_both_sides(
    mock_prompt_cred, mock_confirm, mock_crawl, mock_apply_norm,
    mock_format_summary, mock_write_json, mock_git_commit,
):
    # reconcile_links and derive_interfaces are deliberately NOT mocked here —
    # the bug this covers only exists in how the two compose. Reconciliation
    # collapses the A->B and B->A recordings of one cable into a single link,
    # and derive_interfaces only emits the local ("a") side, so deriving after
    # reconciliation loses the far end's interface record entirely.
    mock_prompt_cred.return_value = Credential(username="admin", password="secret")

    def _facts(serial, name):
        return DeviceFacts(name=name, serial=serial, manufacturer="Cisco", model="m",
                            software_version="v", source="restconf", discovered_via_hop=0)

    def _link(a_serial, a_if, b_host, b_if):
        return NeighborLink(a_device_serial=a_serial, a_interface=a_if, b_device_hostname=b_host,
                             b_interface=b_if, protocol="cdp", discovered_via_hop=0, source="restconf")

    mock_crawl.return_value = CrawlResult(
        visited={"S1": _facts("S1", "sw01"), "S2": _facts("S2", "sw02")},
        links=[_link("S1", "Gi0/1", "sw02", "Gi0/2"), _link("S2", "Gi0/2", "sw01", "Gi0/1")],
        auth_failed=[], unreachable=[],
    )
    mock_confirm.return_value = True
    mock_write_json.return_value = MagicMock()

    discover.main(["--seed", "10.0.0.1"])

    written_result, written_interfaces = mock_write_json.call_args.args
    assert len(written_result.links) == 1  # the cable is still deduped to one link
    assert {(i.device_serial, i.name) for i in written_interfaces} == {
        ("S1", "Gi0/1"), ("S2", "Gi0/2"),
    }


@patch("discover.subprocess.run")
def test_git_commit_force_adds_the_gitignored_output_file(mock_run):
    discover.git_commit(Path("output/20260806T120000Z-discovery.json"))

    add_cmd = mock_run.call_args_list[0].args[0]
    assert add_cmd[:3] == ["git", "add", "-f"]


@patch("discover.subprocess.run")
def test_git_commit_warns_instead_of_raising_when_git_fails(mock_run, capsys):
    mock_run.side_effect = subprocess.CalledProcessError(128, ["git", "add"])

    discover.git_commit(Path("output/run.json"))  # must not raise

    out = capsys.readouterr().out
    assert "Warning: git commit failed" in out
    assert "output/run.json" in out


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_git_commit_actually_commits_a_gitignored_output_file(tmp_path, monkeypatch):
    # Real-git regression test for the composition bug: `.gitignore` contains
    # `output/*.json`, so a plain `git add` of the discovery output is a no-op
    # that exits non-zero — the commit step failed on every single run.
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(args, cwd=repo, check=True,
                                        capture_output=True, text=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")
    run("git", "config", "commit.gpgsign", "false")
    (repo / ".gitignore").write_text("output/*.json\n")
    run("git", "add", ".gitignore")
    run("git", "commit", "-q", "-m", "init")

    (repo / "output").mkdir()
    output_file = Path("output") / "20260806T120000Z-discovery.json"
    (repo / output_file).write_text("{}")

    monkeypatch.chdir(repo)
    discover.git_commit(output_file)

    committed = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"],
                                cwd=repo, capture_output=True, text=True, check=True)
    assert "output/20260806T120000Z-discovery.json" in committed.stdout
