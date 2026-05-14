# =========================================================
# Akai IPL Monitoring Script
# Version: v1.4.0 (Full debug + stage tracing)
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

REDIS_KEY = "akai_status_v4"

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

def send(msg):
    if not WEBHOOK_URL:
        print(msg)
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": msg + "\n\u200b\n"}, timeout=10)
    except Exception as e:
        print("Discord error:", e)

# =========================
# DEBUG helper
# =========================

def debug(page, label):
    print(f"\n========== {label} ==========")
    print("URL:", page.url)

    html = page.content()
    print(html[:2000])

    page.screenshot(path=f"{label}.png", full_page=True)

# =========================
# safe click
# =========================

def click_if_exists(page, locator, name, wait=2000):
    try:
        count = locator.count()
        print(f"🔎 {name} count:", count)

        if count > 0:
            locator.first.click(force=True)
            print(f"🟢 {name} clicked")
            page.wait_for_timeout(wait)
            return True
        else:
            print(f"🟡 {name} not found")
            return False

    except Exception as e:
        print(f"❌ {name} error:", e)
        return False

# =========================
# slot scan
# =========================

def scan(page):
    found = []

    cells = page.locator("div, span, td")

    for i in range(cells.count()):
        try:
            t = cells.nth(i).inner_text().strip()
            if t in ["◎", "△"]:
                found.append(t)
        except:
            pass

    return found

# =========================
# next week
# =========================

def next_week(page):
    btn = page.locator("button:has-text('翌週')")

    print("🔎 next week count:", btn.count())

    if btn.count() == 0:
        print("⛔ no next week")
        return False

    btn.first.click(force=True)
    print("🟢 next week clicked")
    page.wait_for_timeout(3000)
    return True

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

            print("🚀 v1.4.0 start")

            # =========================
            # open
            # =========================
            page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            debug(page, "after_goto")

            # =========================
            # 再診
            # =========================
            click_if_exists(
                page,
                page.locator("[data-id='operation-selection']"),
                "再診",
                3000
            )

            # =========================
            # 予約
            # =========================
            click_if_exists(
                page,
                page.locator("text=予約"),
                "予約",
                4000
            )

            # =========================
            # カテゴリ
            # =========================
            click_if_exists(
                page,
                page.locator("text=当日施術のみ"),
                "カテゴリ",
                2000
            )

            # =========================
            # IPL
            # =========================
            ipl = page.locator("text=IPL")
            print("🔎 IPL count:", ipl.count())

            if ipl.count() > 0:
                ipl.first.click(force=True)
                print("🟢 IPL clicked")
                page.wait_for_timeout(2000)
            else:
                print("❌ IPL not found")
                debug(page, "no_ipl")
                return

            # =========================
            # 確定
            # =========================
            click_if_exists(
                page,
                page.locator("text=確定"),
                "確定",
                5000
            )

            # =========================
            # カレンダー確認
            # =========================
            debug(page, "after_confirm")

            print("🔎 翌週チェック")

            # =========================
            # scan loop
            # =========================
            for w in range(3):

                print(f"\n===== week {w} =====")

                found = scan(page)
                all_found.extend(found)

                print("slot:", found)

                if w == 2:
                    break

                if not next_week(page):
                    break

        except Exception as e:
            print("❌ ERROR:", e)
            debug(page, "error")

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

    msg = ["🟢 Akai IPL監視 v1.4.0"]

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
