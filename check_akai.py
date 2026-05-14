import os
import requests
import redis
from playwright.sync_api import sync_playwright

URL = "https://reservation.medical-force.com/c/aa9268a46f2a4da29f4c98b2aee12475"

WEBHOOK_URL = os.environ.get("WEBHOOK_URL_Akai")
REDIS_URL = os.environ.get("REDIS_URL_Akai")

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
# state detect（最重要）
# -------------------------
def detect_state(page):

    if page.locator("[data-id='operation-selection']").count() > 0:
        return "start"

    if page.locator("text=予約に進む").count() > 0:
        return "reserve"

    if page.locator("text=メニューを確定する").count() > 0:
        return "menu"

    if page.locator("button:has-text('翌週')").count() > 0:
        return "calendar"

    return "unknown"

# -------------------------
# click safe
# -------------------------
def click(page, selector, name, wait=1200):
    loc = page.locator(selector)
    if loc.count() == 0:
        print(f"🟡 {name} not found")
        return False

    loc.first.click(force=True)
    print(f"🟢 {name} clicked")
    page.wait_for_timeout(wait)
    return True

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
            print("🚀 v1.7.0 start")

            # -------------------------
            # open
            # -------------------------
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

            # -------------------------
            # state routing
            # -------------------------
            state = detect_state(page)
            print("🧭 state:", state)

            if state == "start":
                click(page, "[data-id='operation-selection']", "再診")
                click(page, "text=予約に進む", "予約")
                click(page, "text=当日施術のみ", "カテゴリ")

            elif state == "reserve":
                click(page, "text=予約に進む", "予約")
                click(page, "text=当日施術のみ", "カテゴリ")

            elif state == "menu":
                click(page, "button:has-text('メニューを確定する')", "確定")

            elif state == "calendar":
                print("🟢 already calendar")

            # -------------------------
            # IPL（ラジオ or textどっちでも）
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
            # 確定（保険）
            # -------------------------
            if page.locator("button:has-text('メニューを確定する')").count():
                click(page, "button:has-text('メニューを確定する')", "確定")

            # -------------------------
            # カレンダー待ち（最小）
            # -------------------------
            page.wait_for_timeout(2000)

            if page.locator("button:has-text('翌週')").count() == 0:
                print("❌ calendar not found")
                page.screenshot(path="no_calendar.png", full_page=True)
                send("🟡 no calendar")
                return

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

                if next_btn.count() == 0:
                    break

                next_btn.first.click(force=True)
                page.wait_for_timeout(1500)

        finally:
            browser.close()

    all_found = list(dict.fromkeys(all_found))
    print("\nFINAL:", all_found)

    send("🟢 Akai v1.7.0\n" + str(all_found))

if __name__ == "__main__":
    run()
