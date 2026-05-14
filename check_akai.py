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
# date picker
# -------------------------
def select_date_with_ok(page, date_str):

    # open picker
    page.locator("input[aria-label*='Choose date']").first.click()
    page.wait_for_timeout(500)

    # select date
    target = page.locator(f"text={date_str}")
    if target.count() == 0:
        print(f"🟡 date not found: {date_str}")
        return False

    target.first.click()
    print(f"🟢 date selected: {date_str}")

    # OK click
    ok = page.locator("button:has-text('OK')")
    if ok.count() > 0:
        ok.first.click()
        print("🟢 OK clicked")

    # wait render (重要)
    page.wait_for_timeout(2000)

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

    base = datetime.datetime.today()

    targets = [
        base,
        base + datetime.timedelta(days=7),
        base + datetime.timedelta(days=14),
    ]

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        try:
            print("🚀 v1.8.0 start")

            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

            state = detect_state(page)
            print("🧭 state:", state)

            # -------------------------
            # step routing
            # -------------------------
            if state == "start":
                page.locator("[data-id='operation-selection']").first.click()
                print("🟢 再診 clicked")

                page.locator("text=予約に進む").first.click()
                print("🟢 予約 clicked")

            elif state == "reserve":
                page.locator("text=予約に進む").first.click()
                print("🟢 reserve clicked")

            # menu step
            if page.locator("text=メニューを確定する").count() > 0:
                page.locator("button:has-text('メニューを確定する')").first.click()
                print("🟢 menu confirmed")

            page.wait_for_timeout(1500)

            # -------------------------
            # calendar scan loop
            # -------------------------
            for i, d in enumerate(targets):

                date_str = d.strftime("%Y/%m/%d")
                print(f"\n📅 target: {date_str}")

                ok = select_date_with_ok(page, date_str)
                if not ok:
                    continue

                # wait calendar stable
                page.wait_for_timeout(2000)

                found = scan(page)
                all_found.extend(found)

                print("slot:", found)

            # -------------------------
            # result
            # -------------------------
            all_found = list(dict.fromkeys(all_found))

            print("\nFINAL:", all_found)

            send("🟢 Akai v1.8.0\n" + str(all_found))

        finally:
            browser.close()


if __name__ == "__main__":
    run()
