# =========================================================
# Akai IPL Monitor v1.6.0
# Fix: MUI radio (label-driven UI)
# Stable navigation + calendar detection
# =========================================================

import os
import json
import requests
import redis

from playwright.sync_api import sync_playwright

# =========================
# config
# =========================

URL = "https://reservation.medical-force.com/c/aa9268a46f2a4da29f4c98b2aee12475/reservations/new?menu_entrance_id=984c91f4-067b-4bc8-ac8c-861024818292"

WEBHOOK_URL = os.environ.get("WEBHOOK_URL_Akai")
REDIS_URL = os.environ.get("REDIS_URL_Akai")

REDIS_KEY = "akai_status_v6"

# =========================
# redis
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
# notify
# =========================

def send(msg):
    if not WEBHOOK_URL:
        print(msg)
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": msg + "\n\u200b\n"}, timeout=10)
    except Exception as e:
        print("Discord error:", e)

# =========================
# click helper
# =========================

def click(page, selector, name, wait=2000):
    loc = page.locator(selector)
    print(f"🔎 {name} count:", loc.count())

    if loc.count() == 0:
        print(f"🟡 {name} not found")
        return False

    try:
        loc.first.click(force=True)
        print(f"🟢 {name} clicked")
        page.wait_for_timeout(wait)
        return True
    except Exception as e:
        print(f"❌ {name} error:", e)
        return False

# =========================
# calendar detect
# =========================

def is_calendar(page):
    return (
        page.locator("button:has-text('翌週')").count() > 0 or
        page.locator("text=◎").count() > 0 or
        page.locator("text=△").count() > 0
    )

# =========================
# scan
# =========================

def scan(page):
    found = []
    for el in page.locator("div, span, td").all():
        try:
            t = el.inner_text().strip()
            if t in ["◎", "△"]:
                found.append(t)
        except:
            pass
    return found

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

            print("🚀 v1.6.0 start")

            # =========================
            # open
            # =========================
            page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            # =========================
            # 再診
            # =========================
            click(page, "[data-id='operation-selection']", "再診", 2000)

            # =========================
            # 予約に進む
            # =========================
            click(page, "text=予約に進む", "予約", 3000)

            # =========================
            # カテゴリ（存在時のみ）
            # =========================
            click(page, "text=当日施術のみ", "カテゴリ", 1500)

            # =========================
            # IPL（重要：radio禁止・labelクリック）
            # =========================

            ipl_label = page.locator("text=IPL")

            print("🔎 IPL label count:", ipl_label.count())

            if ipl_label.count() == 0:
                print("❌ IPL not found")
                page.screenshot(path="no_ipl.png", full_page=True)
                return

            ipl_label.first.click(force=True)
            print("🟢 IPL selected (label click)")

            page.wait_for_timeout(1500)

            # =========================
            # メニュー確定
            # =========================
            click(page, "button:has-text('メニューを確定する')", "確定", 4000)

            # =========================
            # debug
            # =========================
            print("\n========== AFTER CONFIRM ==========")
            print("URL:", page.url)

            page.wait_for_timeout(3000)

            # =========================
            # calendar check
            # =========================
            if not is_calendar(page):
                print("❌ calendar not detected")
                page.screenshot(path="no_calendar.png", full_page=True)
            else:
                print("🟢 calendar detected")

            # =========================
            # scan weeks
            # =========================
            for w in range(3):

                print(f"\n===== week {w} =====")

                found = scan(page)
                all_found.extend(found)

                print("slot:", found)

                next_btn = page.locator("button:has-text('翌週')")
                print("🔎 next week count:", next_btn.count())

                if next_btn.count() == 0:
                    print("⛔ no next week")
                    break

                next_btn.first.click(force=True)
                page.wait_for_timeout(2500)

        finally:
            browser.close()

    # =========================
    # dedup
    # =========================

    all_found = list(dict.fromkeys(all_found))
    print("\n📦 FINAL:", all_found)

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
            print("Redis error:", e)

    # =========================
    # notify
    # =========================

    msg = ["🟢 Akai IPL監視 v1.6.0"]

    if not changed:
        msg.append("（前回から変更なし）")

    if not all_found:
        msg.append("\n空きなし")
    else:
        msg.append("")
        msg.extend("・" + x for x in all_found)

    send("\n".join(msg))

    print("✅ done")


if __name__ == "__main__":
    run()
