import requests
from typing import Dict, Any
from schemas import NormalizedResult

class Node1Client:
    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        
    def fetch_exercise_data(self, exercise_id: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        response = requests.get(f"{self.base_url}/exercises/{exercise_id}", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
        
    def notify_result(self, result: NormalizedResult):
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        response = requests.post(f"{self.base_url}/submissions/{result.submission_id}/callback", json=result.model_dump(), headers=headers, timeout=10)
        response.raise_for_status()
