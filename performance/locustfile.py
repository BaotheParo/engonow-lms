"""
performance/locustfile.py
=========================
Distributed Locust load test suite simulating 100+ concurrent IELTS candidate evaluations
and deep health checks against the ENGONOW AI Worker & LMS Core.
"""

from locust import HttpUser, task, between, events
import uuid
import json
import logging

logger = logging.getLogger("LocustLoadTest")


class AiWorkerEvaluationUser(HttpUser):
    wait_time = between(1.0, 3.0)

    def on_start(self):
        self.student_id = str(uuid.uuid4())
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer student-test-token",
            "X-User-Role": "ROLE_STUDENT",
            "X-User-Id": self.student_id
        }

    @task(4)
    def submit_writing_task2_essay(self):
        """Simulates IELTS Writing Task 2 essay evaluation submission."""
        submission_id = str(uuid.uuid4())
        payload = {
            "studentId": self.student_id,
            "taskType": "TASK2",
            "promptText": "Some people believe that unpaid community service should be a compulsory part of high school programmes. To what extent do you agree or disagree?",
            "essayText": "Implementing mandatory community service in secondary education has garnered considerable debate. Proponents argue that voluntary service fosters civic responsibility and empathy, while detractors maintain that compulsory participation negates the altruistic spirit of volunteering. In my opinion, integrating structured community engagement into curricula offers profound developmental benefits for students."
        }

        with self.client.post(
            "/api/v1/writing/submissions/submit",
            json=payload,
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in (200, 202):
                response.success()
            else:
                response.failure(f"Failed writing submission with status {response.status_code}: {response.text}")

    @task(2)
    def submit_speaking_part1_attempt(self):
        """Simulates IELTS Speaking claim-check attempt submission."""
        attempt_id = str(uuid.uuid4())
        payload = {
            "attemptId": attempt_id,
            "studentId": self.student_id,
            "part": "PART_1",
            "audioUrl": "https://storage.engonow.com/audio/test-attempt-sample.wav",
            "transcript": "Well, I currently live in a bustling urban area which is famous for its vibrant culture and diverse cuisine."
        }

        with self.client.post(
            "/api/v1/speaking/submit",
            json=payload,
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in (200, 202):
                response.success()
            else:
                response.failure(f"Failed speaking submission with status {response.status_code}: {response.text}")

    @task(1)
    def check_deep_health_endpoint(self):
        """Validates /health response SLA and component status under load."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") in ("UP", "DEGRADED"):
                        response.success()
                    else:
                        response.failure(f"Health returned DOWN under load: {data}")
                except Exception as ex:
                    response.failure(f"Invalid JSON from /health: {ex}")
            else:
                response.failure(f"Health check returned HTTP {response.status_code}")
