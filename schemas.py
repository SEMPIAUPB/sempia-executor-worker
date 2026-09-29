from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class VerdictState(str, Enum):
    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

class SubmissionContract(BaseModel):
    submission_id: str
    exercise_id: str
    source_code: str
    language_id: int
    time_limit: float = Field(..., gt=0.0)
    memory_limit: float = Field(..., gt=0.0)
    correlation_id: str
    version: str = "1.0"
    
class TestCase(BaseModel):
    inputs: str
    expected_outputs: str

class ExerciseData(BaseModel):
    test_cases: List[TestCase]

class NormalizedResult(BaseModel):
    submission_id: str
    state: VerdictState
    judge_status_id: int
    time_used: Optional[float] = None
    memory_used: Optional[float] = None
    error_message: Optional[str] = None
    correlation_id: str
    version: str = "1.0"
