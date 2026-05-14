# =========================================================
# Akai IPL Monitoring Script
# Version: v1.3.0 (DOM resilient + robust selectors)
# =========================================================

import os
import json
import time
import requests
import redis

from playwright.sync_api import sync_playwright

# =========================
# Config
# =========================

URL = "https://reservation.medical-force.com/c/aa9268a46f2a4da29f4c98b2aee12475/reservations/new?menu_entrance_id=984c91f4-067b-4bc8-ac8c-861024818292"

WEBHOOK_URL = os.environ.get("WEBHOOK_URL_Akai")
REDIS_URL = os.environ.get("REDIS_URL_Akai")

REDIS_KEY = "akai_status_v3"

# =========================
# Redis
# =========================

r = None
if REDIS_URL:
    try:
        url = REDIS_URL.replace("redis://", "rediss://", 1)
        r = redis.from_url(url, decode_responses=True, ssl_cert_reqs=None)
        r.ping()
        print("✅ Redis connected")
    except Exception as e:
        print("❌ Redis error:", e)
        r = None

# =========================
# Notify
# =========================

def send_discord(msg):
    if not WEBHOOK_URL:
        print(msg)
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": msg + "\n\u200b\n"}, timeout=10)
    except Exception as e:
        print("Discord error:", e)

# =========================
# Safe click helper
# =========================

def safe_click(page, locator, label, wait=2000):
    try:
        if locator.count() > 0:
            locator.first.click(force=True)
            print(f"🟢 {label}")
            page.wait_for_timeout(wait)
            return True
        else:
            print(f"🟡 {label}なし")
            return False
    except Exception as e:
        print(f"❌ {label}失敗:", e)
        return False

# =========================
# slot scan (完全安全版)
# =========================

def scan_slots(page):
    found = []

    # DOM全体から抽出（MUI対策）
    blocks = page.locator("div, span, td")

    count = blocks.count()

    for i in range(count):
        try:
            txt = blocks.nth(i).inner_text().strip()
            if txt in ["◎", "△"]:
                found.append(txt)
        except:
            pass

    return found

# =========================
# next week click（最強版）
# =========================

def click_next_week(page):
    selectors = [
        "button:has-text('翌週')",
        "text=翌週",
        "role=button[name='翌週']"
    ]

    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.click(force=True)
                print("🟢 翌週クリック")
                page.wait_for_timeout(3000)
                return True
        except:
            continue

    print("⛔ 翌週なし")
    return False

# =========================
# main
# =========================

def run():

    all_found = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        page = browser.new_page()

        try:

            print("🚀 v1.3.0 start")

            # =========================
            # open
            # =========================
            page.goto(URL, timeout=60000)
            page.wait_for_timeout(5000)

            print("URL:", page.url)

            # =========================
            # 再診（存在すれば押す）
            # =========================
            safe_click(
                page,
                page.locator("[data-id='operation-selection']"),
                "再診",
                wait=3000
            )

            # =========================
            # 予約
            # =========================
            safe_click(
                page,
                page.locator("text=予約"),
                "予約に進む",
                wait=4000
            )

            # =========================
            # カテゴリ
            # =========================
            safe_click(
                page,
                page.locator("text=当日施術のみ"),
                "カテゴリ",
                wait=2000
            )

            # =========================
            # IPL（麻酔なし優先）
            # =========================
            ipl_candidates = page.locator("text=IPL")

            if ipl_candidates.count() > 0:
                ipl_candidates.first.click(force=True)
                print("🟢 IPL")
                page.wait_for_timeout(2000)
            else:
                print("❌ IPLなし")
                return

            # =========================
            # 確定
            # =========================
            safe_click(
                page,
                page.locator("text=確定"),
                "確定",
                wait=6000
            )

            # =========================
            # カレンダー判定（重要）
            # =========================
            page.wait_for_timeout(3000)

            if page.locator("button").count() == 0:
                print("❌ UI未ロード")
                return

            print("📅 カレンダー検出")

            # =========================
            # scan 3 weeks
            # =========================
            for w in range(3):

                print(f"week {w}")

                all_found.extend(scan_slots(page))

                if w == 2:
                    break

                if not click_next_week(page):
                    break

        except Exception as e:
            print("❌ Error:", e)
            page.screenshot(path="error.png", full_page=True)

        finally:
            browser.close()

    # =========================
    # dedup
    # =========================

    all_found = list(dict.fromkeys(all_found))

    print("📦 final:", len(all_found))

    # =========================
    # diff
    # =========================

    changed = True

    if r:
        try:
            last = r.get(REDIS_KEY)
            if last:
                old = json.loads(last)
                if set(old) == set(all_found):
                    changed = False

            r.set(REDIS_KEY, json.dumps(all_found))

        except Exception as e:
            print("❌ Redis error:", e)

    # =========================
    # notify
    # =========================

    msg = ["🟢 Akai IPL監視 v1.3.0"]

    if not changed:
        msg.append("（前回から変更なし）")

    if not all_found:
        msg.append("\n空きなし")
    else:
        msg.append("")
        msg.extend("・" + x for x in all_found)

    send_discord("\n".join(msg))

    print("✅ done")


if __name__ == "__main__":
    run()
