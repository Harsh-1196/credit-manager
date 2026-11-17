"""
Production Smoke Test Script for SHG Credit Manager (Phase 7)
Usage:
  python scripts/smoke_test.py --url https://your-production-app.onrender.com
"""

import argparse
import sys
import time

try:
    import httpx
except ImportError:
    print("httpx is required to run smoke tests. Run: pip install httpx")
    sys.exit(1)


def run_smoke_tests(base_url: str, admin_email: str, admin_password: str) -> bool:
    base_url = base_url.rstrip("/")
    print("=" * 80)
    print(f"SHG Credit Manager: Production Smoke Verification -> {base_url}")
    print("=" * 80)

    all_passed = True
    client = httpx.Client(timeout=10.0)

    # 1. Healthcheck: /health
    print("\n1. Testing GET /health...")
    t0 = time.perf_counter()
    try:
        r = client.get(f"{base_url}/health")
        dur_ms = (time.perf_counter() - t0) * 1000.0
        if r.status_code == 200 and r.json().get("status") == "ok":
            print(f"   [PASS] /health responded 200 OK in {dur_ms:.1f}ms")
        else:
            print(f"   [FAIL] /health unexpected response: {r.status_code} {r.text}")
            all_passed = False
    except Exception as e:
        print(f"   [FAIL] Could not connect to /health: {e}")
        all_passed = False

    # 2. Readiness: /ready
    print("\n2. Testing GET /ready (database connectivity)...")
    t0 = time.perf_counter()
    try:
        r = client.get(f"{base_url}/ready")
        dur_ms = (time.perf_counter() - t0) * 1000.0
        if r.status_code == 200 and r.json().get("status") == "ready":
            print(f"   [PASS] /ready responded 200 OK (DB connected) in {dur_ms:.1f}ms")
        else:
            print(f"   [FAIL] /ready unexpected response: {r.status_code} {r.text}")
            all_passed = False
    except Exception as e:
        print(f"   [FAIL] Could not connect to /ready: {e}")
        all_passed = False

    # 3. Prometheus Metrics: /metrics
    print("\n3. Testing GET /metrics (observability exporter)...")
    t0 = time.perf_counter()
    try:
        r = client.get(f"{base_url}/metrics")
        dur_ms = (time.perf_counter() - t0) * 1000.0
        if r.status_code == 200 and "http_request_duration_seconds" in r.text:
            print(f"   [PASS] /metrics exported Prometheus telemetry in {dur_ms:.1f}ms")
        else:
            print(f"   [FAIL] /metrics unexpected response: {r.status_code}")
            all_passed = False
    except Exception as e:
        print(f"   [FAIL] Could not connect to /metrics: {e}")
        all_passed = False

    # 4. Authentication: POST /api/v1/auth/login
    print("\n4. Testing Authentication POST /api/v1/auth/login...")
    t0 = time.perf_counter()
    token = None
    try:
        r = client.post(
            f"{base_url}/api/v1/auth/login",
            json={"email": admin_email, "password": admin_password},
        )
        dur_ms = (time.perf_counter() - t0) * 1000.0
        if r.status_code == 200:
            token = r.json().get("access_token")
            print(f"   [PASS] Authenticated successfully in {dur_ms:.1f}ms")
        else:
            print(f"   [FAIL] Authentication failed: {r.status_code} {r.text}")
            all_passed = False
    except Exception as e:
        print(f"   [FAIL] Login request error: {e}")
        all_passed = False

    # 5. Authenticated Read: GET /api/v1/dashboard
    if token:
        print("\n5. Testing Authenticated Read: GET /api/v1/dashboard...")
        t0 = time.perf_counter()
        try:
            r = client.get(
                f"{base_url}/api/v1/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )
            dur_ms = (time.perf_counter() - t0) * 1000.0
            if r.status_code == 200:
                print(f"   [PASS] Dashboard loaded in {dur_ms:.1f}ms")
            else:
                print(f"   [FAIL] Dashboard returned status {r.status_code}: {r.text}")
                all_passed = False
        except Exception as e:
            print(f"   [FAIL] Dashboard request error: {e}")
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("[SUCCESS] All smoke tests passed! Production deployment is healthy.")
    else:
        print("[FAILURE] One or more smoke tests failed.")
    print("=" * 80)
    return all_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SHG Credit Manager Smoke Test")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of application")
    parser.add_argument("--email", default="admin@shg.org", help="Admin email for auth check")
    parser.add_argument("--password", default="AdminPass123!", help="Admin password for auth check")
    args = parser.parse_args()

    success = run_smoke_tests(args.url, args.email, args.password)
    sys.exit(0 if success else 1)
