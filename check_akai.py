import os
import json
import requests
import redis
from playwright.sync_api import sync_playwright

URL = "https://reservation.medical-force.com/c/aa9268a46f2a4da29f4c98b2aee12475/reservations/new?menu_entrance_id=984c91f4-067b-4bc8-ac8c-861024818292"

WEBHOOK_URL = os.environ.get("WEBHOOK_URL_Akai")
REDIS_URL = os.environ.get("REDIS_URL_Akai")
REDIS_KEY = "akai_status_v6"

# -------------------------
# redis
# -------------------------
r = None
if REDIS_URL:
    try:
        url = REDIS_URL.replace("redis://", "rediss://", 1)
        r = redis.from_url(url, decode_responses=True, ssl_cert_reqs=None)
        r.ping()
        print("✅ Redis connected")
    except Exception as e:
        print("❌ Redis error:", e)

def send(msg):
    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={"content": msg}, timeout=10)
    else:
        print(msg)

# -------------------------
# 安定待ち（完全分離）
# -------------------------
def wait_ready(page):
    # ① DOMロード
    page.wait_for_load_state("domcontentloaded")

    # ② 再診 or 予約 or IPL のいずれかが出るまで待つ
    page.wait_for_function("""
        () => {
            return document.querySelector("[data-id='operation-selection']")
                || document.body.innerText.includes("予約に進む")
                || document.body.innerText.includes("IPL");
        }
    """, timeout=30000)

# -------------------------
# click helper
# -------------------------
def click(page, selector, name, wait=1500):
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

# -------------------------
# calendar detect
# -------------------------
def has_calendar(page):
    return page.locator("button:has-text('翌週')").count() > 0

# -------------------------
# scan
# -------------------------
def scan(page):
    res = []
    for el in page.locator("div, span, td").all():
        try:
            t = el.inner_text().strip()
            if t in ["◎", "△"]:
                res.append(t)
        except:
            pass
    return res

# -------------------------
# main
# -------------------------
def run():

    all_found = []

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        try:
            print("🚀 v1.6.3 start")

            # -------------------------
            # open
            # -------------------------
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            wait_ready(page)

            # -------------------------
            # 再診
            # -------------------------
            click(page, "[data-id='operation-selection']", "再診")

            # -------------------------
            # 予約に進む
            # -------------------------
            click(page, "text=予約に進む", "予約")

            # -------------------------
            # カテゴリ
            # -------------------------
            click(page, "text=当日施術のみ", "カテゴリ")

            # -------------------------
            # IPL（label固定）
            # -------------------------
            ipl = page.locator("text=IPL")
            print("🔎 IPL count:", ipl.count())

            if ipl.count() == 0:
                print("❌ IPL not found")
                page.screenshot(path="no_ipl.png", full_page=True)
                return

            ipl.first.click(force=True)
            print("🟢 IPL selected")

            # -------------------------
            # 確定
            # -------------------------
            click(page, "button:has-text('メニューを確定する')", "確定", 3000)

            # -------------------------
            # カレンダー待機（CSSのみ）
            # -------------------------
            page.wait_for_selector("button:has-text('翌週')", timeout=30000)

            print("🟢 calendar ready")

            # -------------------------
            # scan 3 weeks
            # -------------------------
            for w in range(3):

                print(f"\n===== week {w} =====")

                found = scan(page)
                all_found.extend(found)

                print("slot:", found)

                next_btn = page.locator("button:has-text('翌週')")
                print("next:", next_btn.count())

                if next_btn.count() == 0:
                    break

                next_btn.first.click(force=True)
                page.wait_for_timeout(2000)

        finally:
            browser.close()

    all_found = list(dict.fromkeys(all_found))
    print("\nFINAL:", all_found)

    send("🟢 Akai v1.6.3\n" + str(all_found))

if __name__ == "__main__":
    run()
