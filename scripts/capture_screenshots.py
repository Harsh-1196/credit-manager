"""
Automated Playwright Screenshot Generator (Phase 8)
Generates high-resolution light and dark screenshots for all primary screens:
  1. Dashboard (Screen 2) - Desktop
  2. Meeting Collection (Screen 6) - Desktop (1280x800)
  3. Meeting Collection (Screen 6) - Mobile (360x780)
  4. Member Passbook (Screen 5) - Desktop
  5. Loan Detail (Screen 8) - Desktop
  6. Audit Log & Chain Verification (Screen 11) - Desktop
  7. AI Assistant Drawer (Screen 6b) - Desktop

Usage:
  python scripts/capture_screenshots.py
"""

import http.server
import json
import os
import socketserver
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "frontend" / "dist"
OUT_DIR = ROOT_DIR / "docs" / "screenshots"
PORT = 4173


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files from frontend/dist with SPA fallback to index.html."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    def do_GET(self):
        # Resolve requested path
        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, format, *args):
        # Suppress spammy HTTP request logs
        pass


def start_server():
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", PORT), SPAHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# Mock API Responses
MOCK_USER = {
    "id": "u0000000-0000-0000-0000-000000000001",
    "email": "leader1@shg.org",
    "phone": "9876543210",
    "role": "GROUP_LEADER",
    "is_active": True,
    "group_access": ["g0000000-0000-0000-0000-000000000001"],
    "created_at": "2024-06-01T00:00:00Z",
    "updated_at": "2024-06-01T00:00:00Z",
    "failed_login_count": 0,
}

MOCK_GROUP = {
    "id": "g0000000-0000-0000-0000-000000000001",
    "name": "Pragati Mahila Mandal",
    "village": "Rampur",
    "ward": "Ward 4",
    "district": "Varanasi",
    "formation_date": "2024-06-01",
    "meeting_day": "1st Monday",
    "meeting_frequency": "MONTHLY",
    "bank_account_label": "State Bank of India A/c **4921",
    "status": "ACTIVE",
    "member_count": 12,
    "created_at": "2024-06-01T00:00:00Z",
    "updated_at": "2024-06-01T00:00:00Z",
}

MOCK_DASHBOARD = {
    "role": "GROUP_LEADER",
    "group_dashboard": {
        "shg_id": MOCK_GROUP["id"],
        "shg_name": MOCK_GROUP["name"],
        "as_of_date": "2026-11-17",
        "total_corpus": "284500.00",
        "total_savings": "142000.00",
        "outstanding_principal": "118250.00",
        "repayment_rate": "97.40",
        "overdue_amount": "4350.00",
        "active_loans_count": 5,
        "par_30": "14500.00",
        "par_60": "14500.00",
        "par_90": "0.00",
        "savings_trend": [
            {"month": "Jun", "amount": "18000.00"},
            {"month": "Jul", "amount": "36000.00"},
            {"month": "Aug", "amount": "54000.00"},
            {"month": "Sep", "amount": "72000.00"},
            {"month": "Oct", "amount": "90000.00"},
            {"month": "Nov", "amount": "108000.00"},
        ],
        "disbursals_vs_repayments": [
            {"month": "Jun", "disbursals": "50000.00", "repayments": "8500.00"},
            {"month": "Jul", "disbursals": "25000.00", "repayments": "14200.00"},
            {"month": "Aug", "disbursals": "30000.00", "repayments": "18900.00"},
            {"month": "Sep", "disbursals": "18450.00", "repayments": "21300.00"},
            {"month": "Oct", "disbursals": "0.00", "repayments": "22100.00"},
            {"month": "Nov", "disbursals": "14500.00", "repayments": "23400.00"},
        ],
        "aging_buckets": [
            {"bucket": "Current", "amount": "103750.00", "loan_count": 4},
            {"bucket": "1-30 Days", "amount": "0.00", "loan_count": 0},
            {"bucket": "31-60 Days", "amount": "14500.00", "loan_count": 1},
            {"bucket": "61-90 Days", "amount": "0.00", "loan_count": 0},
            {"bucket": "90+ Days", "amount": "0.00", "loan_count": 0},
        ],
        "collections_due_list": [
            {"member_id": "m1", "member_name": "Sunita Devi", "savings_due": "300.00", "emi_due": "1639.26", "fine_due": "0.00", "total_due": "1939.26"},
            {"member_id": "m2", "member_name": "Radha Devi", "savings_due": "300.00", "emi_due": "0.00", "fine_due": "0.00", "total_due": "300.00"},
            {"member_id": "m3", "member_name": "Meera Patel", "savings_due": "300.00", "emi_due": "0.00", "fine_due": "25.00", "total_due": "325.00"},
            {"member_id": "m4", "member_name": "Geeta Verma", "savings_due": "300.00", "emi_due": "1350.00", "fine_due": "50.00", "total_due": "1700.00"},
            {"member_id": "m5", "member_name": "Kaushalya Devi", "savings_due": "300.00", "emi_due": "0.00", "fine_due": "0.00", "total_due": "300.00"},
        ],
    }
}

MOCK_COLLECTION_SHEET = {
    "meeting_id": "meet-001",
    "meeting_date": "2026-11-17",
    "period": "2026-11",
    "shg_id": MOCK_GROUP["id"],
    "total_expected_savings": "3600.00",
    "total_expected_emi": "2989.26",
    "total_expected_fines": "75.00",
    "total_expected": "6664.26",
    "items": [
        {"member_id": "m1", "member_name": "Sunita Devi", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "1639.26", "loan_repayment_amount": "1639.26", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "1939.26"},
        {"member_id": "m2", "member_name": "Radha Devi", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
        {"member_id": "m3", "member_name": "Meera Patel", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "25.00", "fine_amount": "25.00", "total_due": "325.00"},
        {"member_id": "m4", "member_name": "Geeta Verma", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "1350.00", "loan_repayment_amount": "1350.00", "fine_due": "50.00", "fine_amount": "50.00", "total_due": "1700.00"},
        {"member_id": "m5", "member_name": "Kaushalya Devi", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
        {"member_id": "m6", "member_name": "Pooja Sharma", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
        {"member_id": "m7", "member_name": "Rekha Yadav", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
        {"member_id": "m8", "member_name": "Anita Bind", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
        {"member_id": "m9", "member_name": "Kiran Maurya", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
        {"member_id": "m10", "member_name": "Shanti Devi", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
        {"member_id": "m11", "member_name": "Saroj Tiwari", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
        {"member_id": "m12", "member_name": "Manju Rajbhar", "attendance_status": "PRESENT", "savings_due": "300.00", "savings_amount": "300.00", "emi_due": "0.00", "loan_repayment_amount": "0.00", "fine_due": "0.00", "fine_amount": "0.00", "total_due": "300.00"},
    ],
}

MOCK_MEMBER = {
    "id": "m1",
    "shg_id": MOCK_GROUP["id"],
    "shg_name": MOCK_GROUP["name"],
    "membership_number": "MEM-001",
    "full_name": "Sunita Devi",
    "phone": "9876543201",
    "gender": "FEMALE",
    "joined_on": "2024-06-01",
    "status": "ACTIVE",
    "total_savings": "18000.00",
    "active_loans_count": 1,
    "total_outstanding_loan": "15355.24",
    "passbook_balance": "18000.00",
    "created_at": "2024-06-01T00:00:00Z",
}

MOCK_PASSBOOK = {
    "member_id": "m1",
    "member_name": "Sunita Devi",
    "total_savings": "18000.00",
    "entries": [
        {"id": "pb-6", "entry_date": "2026-11-06", "description": "November regular monthly savings", "source_type": "SAVINGS", "debit": "0.00", "credit": "300.00", "balance": "18000.00"},
        {"id": "pb-5", "entry_date": "2026-10-06", "description": "October regular monthly savings", "source_type": "SAVINGS", "debit": "0.00", "credit": "300.00", "balance": "17700.00"},
        {"id": "pb-4", "entry_date": "2026-09-06", "description": "September regular monthly savings", "source_type": "SAVINGS", "debit": "0.00", "credit": "300.00", "balance": "17400.00"},
        {"id": "pb-3", "entry_date": "2026-08-06", "description": "August regular monthly savings", "source_type": "SAVINGS", "debit": "0.00", "credit": "300.00", "balance": "17100.00"},
        {"id": "pb-2", "entry_date": "2026-07-06", "description": "July regular monthly savings", "source_type": "SAVINGS", "debit": "0.00", "credit": "300.00", "balance": "16800.00"},
        {"id": "pb-1", "entry_date": "2026-06-06", "description": "June inaugural group savings deposit", "source_type": "SAVINGS", "debit": "0.00", "credit": "300.00", "balance": "16500.00"},
    ]
}

MOCK_LOAN_DETAIL = {
    "id": "l1",
    "shg_id": MOCK_GROUP["id"],
    "member_id": "m1",
    "member_name": "Sunita Devi",
    "loan_number": "LN-0001",
    "purpose": "Dairy buffalo purchase & fodder supplies",
    "principal": "18450.00",
    "interest_rate": "12.000",
    "interest_type": "REDUCING",
    "tenure_months": 12,
    "processing_fee": "184.50",
    "status": "ACTIVE",
    "version": 3,
    "can_approve": False,
    "maker_checker_note": "Maker-checker restriction: You created this loan application and cannot approve it. Another leader or admin must approve.",
    "applied_at": "2026-09-06T10:00:00Z",
    "approved_at": "2026-09-08T14:30:00Z",
    "disbursed_at": "2026-09-10T09:15:00Z",
    "first_due_date": "2026-10-06",
    "summary": {
        "principal": "18450.00",
        "principal_paid": "2924.07",
        "principal_outstanding": "15525.93",
        "interest_accrued": "354.45",
        "interest_paid": "354.45",
        "penalties_accrued": "0.00",
        "penalties_paid": "0.00",
        "total_outstanding": "15525.93",
        "next_installment_due_date": "2026-12-06",
        "next_installment_amount": "1639.26",
    },
    "schedule": [
        {"installment_no": 1, "due_date": "2026-10-06", "principal_due": "1454.76", "interest_due": "184.50", "total_due": "1639.26", "principal_paid": "1454.76", "interest_paid": "184.50", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PAID", "days_overdue": 0},
        {"installment_no": 2, "due_date": "2026-11-06", "principal_due": "1469.31", "interest_due": "169.95", "total_due": "1639.26", "principal_paid": "1469.31", "interest_paid": "169.95", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PAID", "days_overdue": 0},
        {"installment_no": 3, "due_date": "2026-12-06", "principal_due": "1484.00", "interest_due": "155.26", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 4, "due_date": "2027-01-06", "principal_due": "1498.84", "interest_due": "140.42", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 5, "due_date": "2027-02-06", "principal_due": "1513.83", "interest_due": "125.43", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 6, "due_date": "2027-03-06", "principal_due": "1528.97", "interest_due": "110.29", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 7, "due_date": "2027-04-06", "principal_due": "1544.26", "interest_due": "95.00", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 8, "due_date": "2027-05-06", "principal_due": "1559.70", "interest_due": "79.56", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 9, "due_date": "2027-06-06", "principal_due": "1575.30", "interest_due": "63.96", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 10, "due_date": "2027-07-06", "principal_due": "1591.05", "interest_due": "48.21", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 11, "due_date": "2027-08-06", "principal_due": "1606.96", "interest_due": "32.30", "total_due": "1639.26", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
        {"installment_no": 12, "due_date": "2027-09-06", "principal_due": "1623.02", "interest_due": "16.23", "total_due": "1639.25", "principal_paid": "0.00", "interest_paid": "0.00", "penalty_paid": "0.00", "penalty_due": "0.00", "status": "PENDING", "days_overdue": 0},
    ],
    "history": [
        {"id": "h-1", "loan_id": "l1", "from_status": "DRAFT", "to_status": "SUBMITTED", "actor_id": "u1", "reason": "Application completed with dairy project plan", "created_at": "2026-09-06T10:00:00Z"},
        {"id": "h-2", "loan_id": "l1", "from_status": "SUBMITTED", "to_status": "APPROVED", "actor_id": "admin-1", "reason": "Approved by general body assembly", "created_at": "2026-09-08T14:30:00Z"},
        {"id": "h-3", "loan_id": "l1", "from_status": "APPROVED", "to_status": "ACTIVE", "actor_id": "admin-1", "reason": "Disbursed via SBI cheque transfer", "created_at": "2026-09-10T09:15:00Z"},
    ],
    "eligibility": {
        "is_eligible": True,
        "has_warnings": False,
        "summary_message": "All 6 group eligibility criteria satisfied.",
        "checks": [
            {"code": "MEMBER_ACTIVE", "name": "Active Member Status", "passed": True, "severity": "BLOCKER", "message": "Member is in active standing."},
            {"code": "CONCURRENT_LOANS", "name": "Concurrent Active Loans", "passed": True, "severity": "BLOCKER", "message": "Member has 1 active loan (cap is 2)."},
            {"code": "SAVINGS_MULTIPLE", "name": "Savings Multiple Cap", "passed": True, "severity": "BLOCKER", "message": "Principal ₹18,450 <= 8x savings ₹18,000."},
            {"code": "TENURE_POLICY", "name": "Tenure Duration Policy", "passed": True, "severity": "BLOCKER", "message": "12 months within group policy (1 to 24m)."},
            {"code": "OVERDUE_REPAYMENTS", "name": "No Overdue Installments", "passed": True, "severity": "BLOCKER", "message": "Member has zero overdue installments."},
            {"code": "GROUP_LIQUIDITY", "name": "Group Cash Sufficiency", "passed": True, "severity": "WARNING", "message": "Group cash balance sufficient for net disbursal."},
        ]
    }
}

MOCK_AUDIT_LOGS = {
    "total": 5,
    "chain_status": {"is_valid": True, "total_events": 148, "broken_rows": 0, "latest_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
    "items": [
        {"id": "a-5", "sequence": 148, "entity_name": "loans", "entity_id": "l1", "action": "LOAN_REPAYMENT", "actor_id": "u1", "actor_email": "leader1@shg.org", "shg_id": MOCK_GROUP["id"], "prev_hash": "a4f8...b12", "row_hash": "c9d2...e44", "created_at": "2026-11-06T11:30:15.120Z"},
        {"id": "a-4", "sequence": 147, "entity_name": "meetings", "entity_id": "meet-001", "action": "BATCH_COLLECTION", "actor_id": "u1", "actor_email": "leader1@shg.org", "shg_id": MOCK_GROUP["id"], "prev_hash": "8f31...a19", "row_hash": "a4f8...b12", "created_at": "2026-11-06T11:28:40.405Z"},
        {"id": "a-3", "sequence": 146, "entity_name": "loans", "entity_id": "l1", "action": "LOAN_DISBURSE", "actor_id": "admin-1", "actor_email": "admin@shg.org", "shg_id": MOCK_GROUP["id"], "prev_hash": "7e14...c22", "row_hash": "8f31...a19", "created_at": "2026-09-10T09:15:22.890Z"},
        {"id": "a-2", "sequence": 145, "entity_name": "loans", "entity_id": "l1", "action": "LOAN_APPROVE", "actor_id": "admin-1", "actor_email": "admin@shg.org", "shg_id": MOCK_GROUP["id"], "prev_hash": "5d01...f90", "row_hash": "7e14...c22", "created_at": "2026-09-08T14:30:05.112Z"},
        {"id": "a-1", "sequence": 144, "entity_name": "loans", "entity_id": "l1", "action": "LOAN_SUBMIT", "actor_id": "u1", "actor_email": "leader1@shg.org", "shg_id": MOCK_GROUP["id"], "prev_hash": "3c88...e11", "row_hash": "5d01...f90", "created_at": "2026-09-06T10:00:18.004Z"},
    ]
}


def handle_api_route(route):
    url = route.request.url
    method = route.request.method

    if "/api/v1/auth/me" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_USER))
    elif "/api/v1/dashboard" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_DASHBOARD))
    elif "/api/v1/groups" in url and "meetings" not in url and "loans" not in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"items": [MOCK_GROUP], "total": 1}))
    elif "collection-sheet" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_COLLECTION_SHEET))
    elif "/api/v1/members/m1/passbook" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_PASSBOOK))
    elif "/api/v1/members/m1" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_MEMBER))
    elif "/api/v1/loans/l1" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_LOAN_DETAIL))
    elif "/api/v1/loans" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps([MOCK_LOAN_DETAIL]))
    elif "/api/v1/audit" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_AUDIT_LOGS))
    elif "/api/v1/ai/chat" in url:
        resp = {
            "content": "Currently in Pragati Mahila Mandal, Geeta Verma has an overdue installment of ₹1,350.00 (past due by 42 days). All other members have active installments in good standing.",
            "tool_calls": [
                {"name": "list_overdue", "arguments": {"shg_id": MOCK_GROUP["id"]}, "result_summary": "1 loan overdue (Geeta Verma)"}
            ]
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(resp))
    else:
        route.fulfill(status=200, content_type="application/json", body=json.dumps({}))


def capture_all_screenshots():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    server = start_server()
    print("=" * 80)
    print("Playwright Automated Screenshot Capture Suite (Phase 8)")
    print(f"Targeting: http://localhost:{PORT}")
    print(f"Output Directory: {OUT_DIR}")
    print("=" * 80)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            # Fallback to system-installed Microsoft Edge on Windows
            browser = p.chromium.launch(channel="msedge", headless=True)

        for theme in ["light", "dark"]:
            print(f"\n[Theme: {theme.upper()}] Capturing screens...")
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()

            # Set route interception for all backend API calls
            page.route("**/api/v1/**", handle_api_route)

            # Apply local storage auth and theme
            page.goto(f"http://localhost:{PORT}/login")
            page.evaluate(f"""
                localStorage.setItem('shg_token', 'mock-token');
                localStorage.setItem('shg_theme', '{theme}');
                if ('{theme}' === 'dark') {{
                    document.documentElement.classList.add('dark');
                    document.documentElement.setAttribute('data-theme', 'dark');
                }} else {{
                    document.documentElement.classList.remove('dark');
                    document.documentElement.setAttribute('data-theme', 'light');
                }}
            """)

            # 1. Dashboard (Screen 2) - Desktop
            page.goto(f"http://localhost:{PORT}/dashboard")
            page.wait_for_timeout(1000)
            dash_path = OUT_DIR / f"dashboard_{theme}.png"
            page.screenshot(path=str(dash_path), full_page=False)
            print(f"  ✓ Captured: {dash_path.name}")

            # 2. Meeting Collection (Screen 6) - Desktop (1280x800)
            page.goto(f"http://localhost:{PORT}/meetings/meet-001/collection")
            page.wait_for_timeout(1000)
            col_d_path = OUT_DIR / f"meeting_collection_desktop_{theme}.png"
            page.screenshot(path=str(col_d_path), full_page=False)
            print(f"  ✓ Captured: {col_d_path.name}")

            # 3. Meeting Collection (Screen 6) - Mobile (360x780)
            page.set_viewport_size({"width": 360, "height": 780})
            page.goto(f"http://localhost:{PORT}/meetings/meet-001/collection")
            page.wait_for_timeout(1000)
            col_m_path = OUT_DIR / f"meeting_collection_360px_{theme}.png"
            page.screenshot(path=str(col_m_path), full_page=False)
            print(f"  ✓ Captured: {col_m_path.name}")

            # Reset viewport for remaining desktop views
            page.set_viewport_size({"width": 1280, "height": 800})

            # 4. Member Passbook (Screen 5)
            page.goto(f"http://localhost:{PORT}/members/m1")
            page.wait_for_timeout(1000)
            pb_path = OUT_DIR / f"passbook_{theme}.png"
            page.screenshot(path=str(pb_path), full_page=False)
            print(f"  ✓ Captured: {pb_path.name}")

            # 5. Loan Detail (Screen 8)
            page.goto(f"http://localhost:{PORT}/loans/l1")
            page.wait_for_timeout(1000)
            ld_path = OUT_DIR / f"loan_detail_{theme}.png"
            page.screenshot(path=str(ld_path), full_page=False)
            print(f"  ✓ Captured: {ld_path.name}")

            # 6. Audit Log & Chain Verification (Screen 11)
            page.goto(f"http://localhost:{PORT}/audit")
            page.wait_for_timeout(1000)
            audit_path = OUT_DIR / f"audit_log_{theme}.png"
            page.screenshot(path=str(audit_path), full_page=False)
            print(f"  ✓ Captured: {audit_path.name}")

            # 7. AI Assistant Drawer (Screen 6b)
            # Navigate to dashboard, then open assistant
            page.goto(f"http://localhost:{PORT}/dashboard")
            page.wait_for_timeout(800)
            # Click AI assistant trigger button in header
            ai_btn = page.locator("button[aria-label*='AI Assistant'], button:has-text('Assistant'), [data-testid='ai-assistant-toggle']").first
            if ai_btn.is_visible():
                ai_btn.click()
                page.wait_for_timeout(800)
            ai_path = OUT_DIR / f"assistant_panel_{theme}.png"
            page.screenshot(path=str(ai_path), full_page=False)
            print(f"  ✓ Captured: {ai_path.name}")

            context.close()

        browser.close()

    server.shutdown()
    print("\n" + "=" * 80)
    print(f"[SUCCESS] All 14 screenshots successfully generated in {OUT_DIR}!")
    print("=" * 80)


if __name__ == "__main__":
    capture_all_screenshots()
