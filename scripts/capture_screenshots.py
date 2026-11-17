"""
Automated Playwright Screenshot Generator (Phase 8)
Captures authentic, high-resolution light and dark screenshots from the live application:
  1. Executive Dashboard (Screen 2) - Desktop
  2. Meeting Collection (Screen 6) - Desktop (1280x800)
  3. Meeting Collection (Screen 6) - Mobile (360x780)
  4. Member Passbook (Screen 5) - Desktop
  5. Loan Detail & Amortization (Screen 8) - Desktop
  6. Cryptographic Audit Trail (Screen 11) - Desktop
  7. Financial Reports & Statements (Screen 10) - Desktop
  8. AI Assistant Drawer (Screen 6b) - Desktop

Usage:
  python scripts/capture_screenshots.py
"""

import os
import sys
import time
from pathlib import Path
import urllib.request
import json

from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "docs" / "screenshots"

# Determine target host (prefer Vite dev server 5173, fallback 3000)
def get_base_url():
    for port in [5173, 3000]:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return f"http://localhost:{port}"
        except Exception:
            continue
    return "http://localhost:5173"


def get_demo_entity_ids(base_url):
    """Logs in and retrieves real seeded IDs for navigation."""
    login_url = f"{base_url}/api/v1/auth/login"
    login_data = json.dumps({"email": "admin@shg.org", "password": "AdminPass123!"}).encode("utf-8")
    req = urllib.request.Request(login_url, data=login_data, headers={"Content-Type": "application/json"})
    
    with urllib.request.urlopen(req) as resp:
        login_res = json.loads(resp.read().decode("utf-8"))
        token = login_res["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # 1. First Group
    req_groups = urllib.request.Request(f"{base_url}/api/v1/groups", headers=headers)
    with urllib.request.urlopen(req_groups) as resp:
        groups = json.loads(resp.read().decode("utf-8"))["items"]
        shg_id = groups[0]["id"]

    # 2. First Meeting
    req_meetings = urllib.request.Request(f"{base_url}/api/v1/groups/{shg_id}/meetings", headers=headers)
    with urllib.request.urlopen(req_meetings) as resp:
        meetings = json.loads(resp.read().decode("utf-8"))
        meeting_id = meetings[0]["id"] if meetings else None

    # 3. First Member
    req_members = urllib.request.Request(f"{base_url}/api/v1/groups/{shg_id}/members", headers=headers)
    with urllib.request.urlopen(req_members) as resp:
        members = json.loads(resp.read().decode("utf-8"))["items"]
        member_id = members[0]["id"] if members else None

    # 4. First Loan
    req_loans = urllib.request.Request(f"{base_url}/api/v1/loans?group_id={shg_id}", headers=headers)
    with urllib.request.urlopen(req_loans) as resp:
        loans = json.loads(resp.read().decode("utf-8"))
        loan_id = loans[0]["id"] if loans else None

    return {
        "shg_id": shg_id,
        "meeting_id": meeting_id,
        "member_id": member_id,
        "loan_id": loan_id,
    }


def capture_all_screenshots():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_url = get_base_url()
    print("=" * 80)
    print("Playwright Live Screenshot Capture Suite")
    print(f"Targeting: {base_url}")
    print(f"Output Directory: {OUT_DIR}")
    print("=" * 80)

    ids = get_demo_entity_ids(base_url)
    print(f"Entities: SHG={ids['shg_id'][:8]}..., Meeting={ids['meeting_id'][:8]}..., Member={ids['member_id'][:8]}..., Loan={ids['loan_id'][:8]}...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)

        for theme in ["light", "dark"]:
            print(f"\n[Theme: {theme.upper()}] Capturing live application views...")
            context = browser.new_context(viewport={"width": 1366, "height": 840})
            page = context.new_page()

            # 1. Log in
            page.goto(f"{base_url}/login")
            page.wait_for_selector("input[type=email]")
            page.fill("input[type=email]", "admin@shg.org")
            page.fill("input[type=password]", "AdminPass123!")
            page.click("button[type=submit]")
            page.wait_for_url("**/groups", timeout=10000)

            # Apply theme
            if theme == "dark":
                page.evaluate("""
                    document.documentElement.setAttribute('data-theme', 'dark');
                    document.documentElement.classList.add('dark');
                    localStorage.setItem('shg_theme', 'dark');
                """)
            else:
                page.evaluate("""
                    document.documentElement.setAttribute('data-theme', 'light');
                    document.documentElement.classList.remove('dark');
                    localStorage.setItem('shg_theme', 'light');
                """)

            # 1. Dashboard (Screen 2) - Desktop
            page.goto(f"{base_url}/dashboard")
            page.wait_for_selector("h1, h2, h3")
            page.wait_for_timeout(2500)
            dash_path = OUT_DIR / f"dashboard_{theme}.png"
            page.screenshot(path=str(dash_path), full_page=False)
            print(f"  ✓ Captured: {dash_path.name} ({dash_path.stat().st_size:,} bytes)")

            # 2. Meeting Collection (Screen 6) - Desktop
            if ids["meeting_id"]:
                page.goto(f"{base_url}/meetings/{ids['meeting_id']}/collection")
                page.wait_for_selector("table, [role='grid']")
                page.wait_for_timeout(2000)
                col_d_path = OUT_DIR / f"meeting_collection_desktop_{theme}.png"
                page.screenshot(path=str(col_d_path), full_page=False)
                print(f"  ✓ Captured: {col_d_path.name} ({col_d_path.stat().st_size:,} bytes)")

            # 3. Meeting Collection (Screen 6) - Mobile (360x780)
            if ids["meeting_id"]:
                page.set_viewport_size({"width": 360, "height": 780})
                page.goto(f"{base_url}/meetings/{ids['meeting_id']}/collection")
                page.wait_for_timeout(2000)
                col_m_path = OUT_DIR / f"meeting_collection_360px_{theme}.png"
                page.screenshot(path=str(col_m_path), full_page=False)
                print(f"  ✓ Captured: {col_m_path.name} ({col_m_path.stat().st_size:,} bytes)")
                # Reset viewport
                page.set_viewport_size({"width": 1366, "height": 840})

            # 4. Member Passbook (Screen 5)
            if ids["member_id"]:
                page.goto(f"{base_url}/members/{ids['member_id']}")
                page.wait_for_timeout(2000)
                pb_path = OUT_DIR / f"passbook_{theme}.png"
                page.screenshot(path=str(pb_path), full_page=False)
                print(f"  ✓ Captured: {pb_path.name} ({pb_path.stat().st_size:,} bytes)")

            # 5. Loan Detail (Screen 8)
            if ids["loan_id"]:
                page.goto(f"{base_url}/loans/{ids['loan_id']}")
                page.wait_for_timeout(2000)
                ld_path = OUT_DIR / f"loan_detail_{theme}.png"
                page.screenshot(path=str(ld_path), full_page=False)
                print(f"  ✓ Captured: {ld_path.name} ({ld_path.stat().st_size:,} bytes)")

            # 6. Audit Log & Chain Verification (Screen 11)
            page.goto(f"{base_url}/audit")
            page.wait_for_timeout(2000)
            audit_path = OUT_DIR / f"audit_log_{theme}.png"
            page.screenshot(path=str(audit_path), full_page=False)
            print(f"  ✓ Captured: {audit_path.name} ({audit_path.stat().st_size:,} bytes)")

            # 7. Reports & Financial Statements (Screen 10)
            page.goto(f"{base_url}/reports")
            page.wait_for_timeout(2500)
            rep_path = OUT_DIR / f"reports_{theme}.png"
            page.screenshot(path=str(rep_path), full_page=False)
            print(f"  ✓ Captured: {rep_path.name} ({rep_path.stat().st_size:,} bytes)")

            # 8. AI Assistant Drawer (Screen 6b)
            page.goto(f"{base_url}/dashboard")
            page.wait_for_timeout(1500)
            ai_btn = page.locator("button[aria-label*='AI Assistant'], button:has-text('Assistant'), [data-testid='ai-assistant-toggle']").first
            if ai_btn.is_visible():
                ai_btn.click()
                page.wait_for_timeout(1000)
            ai_path = OUT_DIR / f"assistant_panel_{theme}.png"
            page.screenshot(path=str(ai_path), full_page=False)
            print(f"  ✓ Captured: {ai_path.name} ({ai_path.stat().st_size:,} bytes)")

            context.close()

        browser.close()

    print("\n" + "=" * 80)
    print(f"[SUCCESS] All screenshots successfully generated from live application!")
    print("=" * 80)


if __name__ == "__main__":
    capture_all_screenshots()
