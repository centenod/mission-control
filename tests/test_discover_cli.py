# tests/test_discover_cli.py
from unittest.mock import patch, MagicMock

from connectors.cisco.models import Credential
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
    assert second_call_kwargs["credential_sets"] == [cred1, cred2]
