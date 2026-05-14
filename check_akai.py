import os
import time
import datetime
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
# state detect
# -------------------------
def detect_state(page):

    if page.locator("[data-id='operation-selection']").count() > 0:
        return "start"

    if page.locator("text=予約に進む").count() > 0:
        return "reserve"

    if page.locator("text=メニューを確定する").count() > 0:
        return "menu"

    return "calendar"


# -------------------------
# safe click
# -------------------------
def safe_click(locator, label=""):
    try:
        if locator.count() == 0:
            print(f"🟡 not found: {label}")
            return False

        locator.first.click(timeout=5000, force=True)
        print(f"🟢 clicked: {label}")
        return True

    except Exception as e:
        print(f"❌ click failed {label}: {e}")
        return False


# -------------------------
# date picker (fixed)
# -------------------------
def select_date_with_ok(page, date_str):

    print(f"📅 selecting: {date_str}")

    # ① open picker（ここが重要）
    picker = page.locator("input[aria-label*='Choose date']").first

    if picker.count() == 0:
        print("❌ date picker not found")
        return False

    try:
        picker.click(timeout=5000, force=True)
    except:
        print("⚠️ picker click fallback")
        page.locator("input").first.click(force=True)

    page.wait_for_timeout(800)

    # ② wait popup
    page.wait_for_timeout(800)

    # ③ select date
    target = page.locator(f"text={date_str}")

    if target.count() == 0:
        print(f"🟡 date not found: {date_str}")
        return False

    target.first.click()
    print("🟢 date selected")

    # ④ OK
    ok = page.locator("button:has-text('OK')")

    if ok.count() > 0:
        ok.first.click()
        print("🟢 OK clicked")

    # ⑤ render wait
    page.wait_for_timeout(2000)

    return True


# -------------------------
# scan
# -------------------------
def scan(page):

    results = []

    for el in page.locator("div, span, td").all():
        try:
            t = el.inner_text().strip()
            if t in ["◎", "△"]:
                results.append(t)
        except:
            pass

    return results


# -------------------------
# main
# -------------------------
def run():

    base = datetime.datetime.today()

    targets = [
        base,
        base + datetime.timedelta(days=7),
        base + datetime.timedelta(days=14),
    ]

    all_found = []

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        try:
            print("🚀 v1.8.1 start")

            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

            state = detect_state(page)
            print("🧭 state:", state)

            # -------------------------
            # step flow
            # -------------------------
            if state == "start":
                safe_click(page.locator("[data-id='operation-selection']"), "再診")
                safe_click(page.locator("text=予約に進む"), "予約")

            elif state == "reserve":
                safe_click(page.locator("text=予約に進む"), "予約")

            if page.locator("text=メニューを確定する").count() > 0:
                safe_click(page.locator("button:has-text('メニューを確定する')"), "メニュー確定")

            page.wait_for_timeout(1500)

            # -------------------------
            # calendar loop
            # -------------------------
            for d in targets:

                date_str = d.strftime("%Y/%m/%d")

                ok = select_date_with_ok(page, date_str)
                if not ok:
                    continue

                found = scan(page)

                print("slot:", found)

                all_found.extend(found)

            # -------------------------
            # final
            # -------------------------
            all_found = list(dict.fromkeys(all_found))

            print("\nFINAL:", all_found)

            send("🟢 Akai v1.8.1\n" + str(all_found))

        finally:
            browser.close()


if __name__ == "__main__":
    run()
