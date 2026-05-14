# =========================================================
# Akai IPL Monitoring Script
# Version: v1.1.0 (State Debug + Robust Flow)
# =========================================================

import os
import re
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

REDIS_KEY = "akai_status"

# =========================
# Redis
# =========================

r = None

if REDIS_URL:
    try:
        url = REDIS_URL.replace("redis://", "rediss://", 1) if REDIS_URL.startswith("redis://") else REDIS_URL
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
# Debug dump（超重要）
# =========================

def debug_dump(page, label="debug"):
    print(f"\n========== {label.upper()} ==========")
    print("URL:", page.url)

    try:
        html = page.content()
        print(html[:2000])
    except:
        print("content read failed")

    try:
        page.screenshot(path=f"{label}.png", full_page=True)
        print(f"📸 screenshot saved: {label}.png")
    except:
        print("screenshot failed")

    print("================================\n")

# =========================
# slot scan
# =========================

def scan_slots(page):
    found = []
    elems = page.locator("text=◎, text=△")

    for i in range(elems.count()):
        try:
            found.append(elems.nth(i).inner_text().strip())
        except:
            pass

    return found

# =========================
# click next week
# =========================

def click_next(page):
    btn = page.locator("button:has-text('翌週')").first

    if btn.count() == 0:
        print("⛔ 翌週なし")
        return False

    btn.click(force=True)
    page.wait_for_timeout(3000)
    return True

# =========================
# main
# =========================

def run():

    all_found = []

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        try:

            print("🚀 open v1.1.0")

            # =========================
            # load
            # =========================
            page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            debug_dump(page, "after_goto")

            # =========================
            # 再診（存在確認型）
            # =========================
            print("🟢 再診チェック")

            btn = page.locator("[data-id='operation-selection']")

            print("再診 count:", btn.count())

            if btn.count() == 0:
                debug_dump(page, "no_revisit_button")
                return

            btn.first.click(force=True)

            page.wait_for_timeout(3000)

            # =========================
            # 予約に進む
            # =========================
            print("🟢 予約に進む")

            page.get_by_role("button", name=re.compile("予約")).first.click(force=True)
            page.wait_for_timeout(5000)

            # =========================
            # カテゴリ
            # =========================
            print("🟢 カテゴリ")

            cat = page.locator("text=当日施術のみ")

            print("カテゴリ count:", cat.count())

            if cat.count() == 0:
                debug_dump(page, "no_category")
                return

            cat.first.click(force=True)
            page.wait_for_timeout(2000)

            # =========================
            # IPL
            # =========================
            print("🟢 IPL")

            ipl = page.locator("text=IPL")

            print("IPL count:", ipl.count())

            if ipl.count() == 0:
                debug_dump(page, "no_ipl")
                return

            ipl.first.click(force=True)
            page.wait_for_timeout(2000)

            # =========================
            # 確定
            # =========================
            print("🟢 確定")

            page.get_by_role("button", name=re.compile("確定")).first.click(force=True)

            # カレンダー待機（状態ベース）
            page.wait_for_timeout(6000)

            debug_dump(page, "after_confirm")

            # 翌週存在チェック
            if page.locator("button:has-text('翌週')").count() == 0:
                print("⛔ カレンダー未表示")
                debug_dump(page, "no_calendar")
                return

            print("📅 カレンダーOK")

            # =========================
            # scan
            # =========================
            for w in range(3):

                print(f"week {w}")

                all_found.extend(scan_slots(page))

                if w == 2:
                    break

                if not click_next(page):
                    break

        except Exception as e:
            print("❌ Error:", e)
            debug_dump(page, "error")

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

    is_changed = True

    if r:
        try:
            last = r.get(REDIS_KEY)

            if last:
                old = json.loads(last)
                if set(old) == set(all_found):
                    is_changed = False

            r.set(REDIS_KEY, json.dumps(all_found))

        except Exception as e:
            print("❌ Redis error:", e)

    # =========================
    # notify
    # =========================

    msg = [f"🟢 Akai IPL監視 v1.1.0"]

    if not is_changed:
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
