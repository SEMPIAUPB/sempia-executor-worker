import pytest
from unittest.mock import patch, MagicMock

from schemas import SubmissionContract, VerdictState, NormalizedResult
from judge0 import Judge0Adapter, Judge0Error
from worker import judge_submission

@pytest.fixture
def mock_contract():
    return {
        "submission_id": "sub_1",
        "exercise_id": "ex_1",
        "source_code": "print('hello')",
        "language_id": 71,
        "time_limit": 1.0,
        "memory_limit": 128.0,
        "correlation_id": "corr_1",
        "version": "1.0"
    }

@patch('worker.node1_client.fetch_exercise_data')
@patch('worker.judge0_adapter.evaluate')
@patch('worker.node1_client.notify_result')
def test_judge_submission_accepted(mock_notify, mock_evaluate, mock_fetch, mock_contract):
    mock_fetch.return_value = {
        "test_cases": [{"input_data": "", "expected_output": "hello\n"}]
    }
    mock_evaluate.return_value = {
        "state": VerdictState.ACCEPTED,
        "judge_status_id": 3,
        "time_used": 0.1,
        "memory_used": 10.0,
        "error_message": None
    }

    # Call task synchronously
    judge_submission(mock_contract)

    # Asserts
    mock_evaluate.assert_called_once()
    mock_notify.assert_called_once()
    
    # Check what was sent to notify_result
    result_arg = mock_notify.call_args[0][0]
    assert isinstance(result_arg, NormalizedResult)
    assert result_arg.state == VerdictState.ACCEPTED
    assert result_arg.submission_id == "sub_1"

@patch('worker.node1_client.fetch_exercise_data')
@patch('worker.judge0_adapter.evaluate')
@patch('worker.node1_client.notify_result')
def test_judge_submission_wrong_answer(mock_notify, mock_evaluate, mock_fetch, mock_contract):
    mock_fetch.return_value = {
        "test_cases": [{"input_data": "", "expected_output": "hello\n"}]
    }
    mock_evaluate.return_value = {
        "state": VerdictState.WRONG_ANSWER,
        "judge_status_id": 4,
        "time_used": 0.1,
        "memory_used": 10.0,
        "error_message": None
    }

    judge_submission(mock_contract)

    mock_notify.assert_called_once()
    result_arg = mock_notify.call_args[0][0]
    assert result_arg.state == VerdictState.WRONG_ANSWER

@patch('worker.node1_client.fetch_exercise_data')
@patch('worker.judge0_adapter.evaluate')
def test_judge_submission_infrastructure_error(mock_evaluate, mock_fetch, mock_contract):
    mock_fetch.return_value = {
        "test_cases": [{"input_data": "", "expected_output": "hello\n"}]
    }
    mock_evaluate.side_effect = Judge0Error("Connection refused")

    # Since it's a celery task, raising a retry is expected or exception if unhandled
    with patch('worker.judge_submission.retry') as mock_retry:
        mock_retry.side_effect = Exception("Retry Triggered")
        with pytest.raises(Exception, match="Retry Triggered"):
            judge_submission(mock_contract)

@patch('worker.node1_client.fetch_exercise_data')
@patch('worker.node1_client.notify_result')
def test_judge_submission_invalid_contract(mock_notify, mock_fetch):
    # Missing required fields should raise an error and notify Node1 as INTERNAL_ERROR if correlation_id is present
    invalid_contract = {
        "submission_id": "sub_err",
        "correlation_id": "corr_err"
    }

    with pytest.raises(Exception):
         judge_submission(invalid_contract)
    
    mock_notify.assert_called_once()
    res = mock_notify.call_args[0][0]
    assert res.state == VerdictState.INTERNAL_ERROR
