import os
import logging
from celery import Celery
from dotenv import load_dotenv

from schemas import SubmissionContract, NormalizedResult, VerdictState, ExerciseData, TestCase
from judge0 import Judge0Adapter, Judge0Error
from api_client import Node1Client

load_dotenv()

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
JUDGE0_API_URL = os.getenv("JUDGE0_API_URL", "http://localhost:2358")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "secret")

celery_app = Celery("sempia_worker", broker=CELERY_BROKER_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_default_queue="judge_submissions",
    task_acks_late=True, # Prevent losing tasks on worker crash
    worker_prefetch_multiplier=1
)

judge0_adapter = Judge0Adapter(JUDGE0_API_URL)
node1_client = Node1Client(API_BASE_URL, API_AUTH_TOKEN)

import outbox
outbox.init_db()

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Runs every 10 seconds to flush outbox
    sender.add_periodic_task(10.0, flush_outbox.s(), name='flush-outbox-every-10s')

@celery_app.task
def flush_outbox():
    events = outbox.get_pending_events()
    for event in events:
        try:
            logger.info(f"Retrying outbox event for submission {event['submission_id']}")
            node1_client.notify_result(NormalizedResult(**event['payload']))
            outbox.mark_event_processed(event['id'])
            logger.info(f"Successfully processed outbox event {event['id']}")
        except Exception as e:
            logger.error(f"Failed to flush outbox event {event['id']}: {e}")


@celery_app.task(bind=True, max_retries=3)
def judge_submission(self, contract_data: dict):
    logger.info(f"Received submission: {contract_data.get('submission_id')}")
    
    try:
        # 1. Parse and validate contract
        contract = SubmissionContract(**contract_data)
        
        # 2. Fetch exercise test cases from Node 1
        exercise_response = node1_client.fetch_exercise_data(contract.exercise_id)
        exercise_data = ExerciseData(**exercise_response)
        
        # 3. Evaluate against Judge0
        # If there are multiple test cases, evaluate sequentially and aggregate.
        # For simplicity, we assume we stop at the first non-ACCEPTED or aggregate times.
        overall_state = VerdictState.ACCEPTED
        max_time = 0.0
        max_memory = 0.0
        overall_status_id = 3
        error_msg = ""
        
        for tc in exercise_data.test_cases:
            result = judge0_adapter.evaluate(
                source_code=contract.source_code,
                language_id=contract.language_id,
                input_data=tc.inputs,
                expected_output=tc.expected_outputs,
                time_limit=contract.time_limit,
                memory_limit=contract.memory_limit
            )
            
            max_time = max(max_time, result["time_used"])
            max_memory = max(max_memory, result["memory_used"])
            
            if result["state"] != VerdictState.ACCEPTED:
                overall_state = result["state"]
                overall_status_id = result["judge_status_id"]
                error_msg = result["error_message"]
                break # Short-circuit
        
        # 4. Save to Outbox and try to notify Node 1
        normalized_res = NormalizedResult(
            submission_id=contract.submission_id,
            state=overall_state,
            judge_status_id=overall_status_id,
            time_used=max_time,
            memory_used=max_memory,
            error_message=error_msg,
            correlation_id=contract.correlation_id,
            version=contract.version
        )
        
        outbox.save_to_outbox(contract.submission_id, normalized_res.model_dump())
        
        # Trigger an immediate flush, but don't crash the task if Node 1 is down
        try:
            flush_outbox()
            logger.info(f"Successfully judged submission {contract.submission_id}: {overall_state}")
        except Exception as e:
            logger.warning(f"Could not immediately notify Node 1, will retry via Outbox. Error: {e}")
            
    except Judge0Error as e:
        logger.error(f"Infrastructure error during evaluation: {e}")
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
        
    except Exception as e:
        logger.error(f"Unexpected error processing submission {contract_data.get('submission_id')}: {e}")
        # In case of internal error that is not retryable (e.g. invalid contract, node1 API changes)
        # Notify Node 1 of INTERNAL ERROR if possible
        try:
            if "submission_id" in contract_data and "correlation_id" in contract_data:
                err_res = NormalizedResult(
                    submission_id=contract_data["submission_id"],
                    state=VerdictState.INTERNAL_ERROR,
                    judge_status_id=13,
                    error_message=str(e)[:500],
                    correlation_id=contract_data["correlation_id"]
                )
                node1_client.notify_result(err_res)
        except:
            pass
        raise
