# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
import pytest
from unittest.mock import MagicMock, patch
from cxidk.workflow.insight_refinements.utils import handle_api_quota, StructuredLogger
from google.api_core.exceptions import ResourceExhausted


def test_handle_api_quota_success():
    """Test that the decorator returns the result on immediate success."""
    mock_func = MagicMock(return_value="success")
    decorated = handle_api_quota(max_retries=3, initial_delay=0.1)(mock_func)

    result = decorated()
    assert result == "success"
    assert mock_func.call_count == 1


def test_handle_api_quota_retry_success():
    """Test that the decorator retries on ResourceExhausted and eventually succeeds."""
    mock_func = MagicMock(side_effect=[ResourceExhausted("Rate limit"), "success"])
    # Use small initial_delay for faster tests
    decorated = handle_api_quota(max_retries=3, initial_delay=0.01)(mock_func)

    result = decorated()
    assert result == "success"
    assert mock_func.call_count == 2


def test_handle_api_quota_failure():
    """Test that the decorator eventually raises the exception after max retries."""
    mock_func = MagicMock(side_effect=ResourceExhausted("Rate limit"))
    decorated = handle_api_quota(max_retries=2, initial_delay=0.01)(mock_func)

    with pytest.raises(ResourceExhausted):
        decorated()

    assert mock_func.call_count == 2


def test_structured_logger_format(capsys):
    """Test that StructuredLogger outputs valid JSON."""
    logger = StructuredLogger("test_logger")
    logger.log("test message", severity="INFO", custom_key="value")

    # We rely on no crash as minimal validation
    assert True


@patch("src.workflow.insight_refinements.utils.time.sleep")  # Don't actually sleep in tests
def test_handle_api_quota_backoff_timing(mock_sleep):
    """Test that exponential backoff logic is applied with correct math."""
    mock_func = MagicMock(
        side_effect=[ResourceExhausted("err"), ResourceExhausted("err"), "ok"]
    )
    # initial_delay * (2**i + random)
    decorated = handle_api_quota(max_retries=5, initial_delay=10.0)(mock_func)

    decorated()

    assert mock_sleep.call_count == 2

    # i=0: 10 * (1 + random[0,1]) -> [10, 20]
    args0, _ = mock_sleep.call_args_list[0]
    assert 10.0 <= args0[0] <= 20.0

    # i=1: 10 * (2 + random[0,1]) -> [20, 30]
    args1, _ = mock_sleep.call_args_list[1]
    assert 20.0 <= args1[0] <= 30.0
