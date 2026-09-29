import requests
import time
from typing import Dict, Any, List
from schemas import VerdictState

class Judge0Error(Exception):
    pass

class Judge0Adapter:
    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        
    def _map_status(self, status_id: int) -> VerdictState:
        # https://ce.judge0.com/#statuses
        if status_id == 3:
            return VerdictState.ACCEPTED
        elif status_id == 4:
            return VerdictState.WRONG_ANSWER
        elif status_id == 5:
            return VerdictState.TIME_LIMIT_EXCEEDED
        elif status_id == 6:
            return VerdictState.COMPILATION_ERROR
        elif status_id in (7, 8, 9, 10, 11, 12):
            return VerdictState.RUNTIME_ERROR
        elif status_id == 13:
            return VerdictState.INTERNAL_ERROR
        else:
            return VerdictState.INTERNAL_ERROR

    def evaluate(self, source_code: str, language_id: int, input_data: str, expected_output: str, time_limit: float, memory_limit: float) -> Dict[str, Any]:
        """
        Envía el código a evaluar y espera de forma síncrona/polling el resultado.
        """
        payload = {
            "source_code": source_code,
            "language_id": language_id,
            "stdin": input_data,
            "expected_output": expected_output,
            "cpu_time_limit": time_limit,
            "memory_limit": memory_limit * 1024, # Judge0 expects KB
            "wall_time_limit": time_limit * 3, # extra buffer
        }
        
        try:
            response = requests.post(f"{self.api_url}/submissions?base64_encoded=false&wait=false", json=payload, timeout=5)
            response.raise_for_status()
            token = response.json().get("token")
        except requests.RequestException as e:
            raise Judge0Error(f"Error connecting to Judge0: {str(e)}")
            
        if not token:
            raise Judge0Error("No token returned by Judge0")
            
        # Poll for result
        for _ in range(30):
            try:
                res = requests.get(f"{self.api_url}/submissions/{token}?base64_encoded=false", timeout=10)
                res.raise_for_status()
                data = res.json()
                
                status_id = data.get("status", {}).get("id")
                # 1=In Queue, 2=Processing
                if status_id not in (1, 2):
                    state = self._map_status(status_id)
                    time_used = float(data.get("time") or 0.0)
                    memory_used = float(data.get("memory") or 0.0)
                    error_msg = data.get("stderr") or data.get("compile_output") or ""
                    
                    return {
                        "state": state,
                        "judge_status_id": status_id,
                        "time_used": time_used,
                        "memory_used": memory_used,
                        "error_message": error_msg[:1000] # truncate
                    }
            except requests.RequestException:
                pass # Retry on temporary network issues while polling
                
            time.sleep(1)
            
        raise Judge0Error("Timeout waiting for Judge0 evaluation")
