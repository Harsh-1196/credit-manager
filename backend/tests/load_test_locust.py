"""
Locust Load Testing Suite for SHG Credit Manager (Phase 7 / SPEC Section 14 & 16)
Scenarios:
  (a) Concurrent repayments against one loan (100+ users)
  (b) Mixed read load on list and dashboard endpoints
  (c) 20-member batch collections
"""

import random
import uuid
from locust import HttpUser, task, between, events


class SHGLoadTestUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Authenticate user and obtain JWT token for API requests."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": "admin@shg.org", "password": "AdminPass123!"},
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {token}"}
        else:
            self.headers = {}

        # Default test SHG ID and active loan ID (can be overridden via environment)
        self.shg_id = "shg-demo-1"
        self.loan_id = "loan-demo-1"
        self.meeting_id = "meeting-demo-1"

    # -------------------------------------------------------------------------
    # Scenario (a): Concurrent Repayments against one loan
    # -------------------------------------------------------------------------
    @task(3)
    def concurrent_repayment(self):
        """Simulate concurrent repayment requests with unique idempotency keys."""
        idem_key = f"locust-repay-{uuid.uuid4().hex}"
        payload = {
            "amount": "100.00",
            "payment_date": "2026-11-17",
            "notes": "Locust automated repayment",
            "idempotency_key": idem_key,
        }
        self.client.post(
            f"/api/v1/shgs/{self.shg_id}/loans/{self.loan_id}/repay",
            json=payload,
            headers={**self.headers, "Idempotency-Key": idem_key},
            name="/loans/[id]/repay",
        )

    # -------------------------------------------------------------------------
    # Scenario (b): Mixed read load on list and dashboard endpoints
    # -------------------------------------------------------------------------
    @task(10)
    def read_dashboard(self):
        """Read group executive dashboard."""
        self.client.get(
            f"/api/v1/shgs/{self.shg_id}/dashboard",
            headers=self.headers,
            name="/dashboard",
        )

    @task(8)
    def read_loans_list(self):
        """Read loans list with filtering."""
        status = random.choice(["ACTIVE", "OVERDUE", "SUBMITTED", "CLOSED"])
        self.client.get(
            f"/api/v1/shgs/{self.shg_id}/loans?status={status}",
            headers=self.headers,
            name="/loans?status",
        )

    @task(6)
    def read_reports(self):
        """Read reports preview."""
        self.client.get(
            f"/api/v1/reports/group-dashboard?shg_id={self.shg_id}&format=json",
            headers=self.headers,
            name="/reports/group-dashboard",
        )

    # -------------------------------------------------------------------------
    # Scenario (c): 20-member batch collection
    # -------------------------------------------------------------------------
    @task(2)
    def batch_collections(self):
        """Post a 20-member batch collection."""
        idem_key = f"locust-batch-{uuid.uuid4().hex}"
        collections = []
        for i in range(20):
            collections.append(
                {
                    "member_id": f"mem-{i:03d}",
                    "attendance_status": "PRESENT",
                    "savings_amount": "300.00",
                    "loan_repayment_amount": "0.00",
                    "fine_amount": "0.00",
                }
            )
        payload = {
            "meeting_id": self.meeting_id,
            "period": "2026-11",
            "collections": collections,
            "idempotency_key": idem_key,
        }
        self.client.post(
            f"/api/v1/shgs/{self.shg_id}/meetings/{self.meeting_id}/collections",
            json=payload,
            headers={**self.headers, "Idempotency-Key": idem_key},
            name="/meetings/[id]/collections (20 members)",
        )
