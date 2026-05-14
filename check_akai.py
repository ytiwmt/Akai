import os
import re
import json
import time
import requests
import redis

from playwright.sync_api import sync_playwright

# =========================
# 設定
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

        r = redis.from_url(
            url,
            decode_responses=True,
            ssl_cert_reqs=None
        )

        r.ping()
        print("✅ Redis connected")

    except Exception as e:
        print("❌ Redis error:", e)
        r = None

# =========================
# Discord
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
# ◎取得
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
# 翌週
# =========================

def click_next(page):
    btn = page.locator("button:has-text('翌週')").first

    if btn.count() == 0:
        print("⛔ 翌週なし")
        return False

    btn.click(force=True)
    page.wait_for_timeout(4000)
    return True

# =========================
# メイン
# =========================

def run():

    all_found = []

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        try:

            print("🚀 open")
            page.goto(URL, timeout=60000)
            page.wait_for_timeout(5000)

            # =========================
            # 再診（ここは最重要・最小）
            # =========================
            print("🟢 再診")

            page.locator("[data-id='operation-selection']").first.click(force=True)
            page.wait_for_timeout(2000)

            # =========================
            # 予約に進む
            # =========================
            print("🟢 予約に進む")

            page.get_by_role("button", name=re.compile("予約")).first.click(force=True)
            page.wait_for_timeout(5000)

            # =========================
            # カテゴリ展開（重要）
            # =========================
            print("🟢 カテゴリ展開")

            page.get_by_text("当日施術のみ").first.click(force=True)
            page.wait_for_timeout(2000)

            # =========================
            # IPL選択
            # =========================
            print("🟢 IPL")

            page.locator("label").filter(has_text="IPL").first.click(force=True)
            page.wait_for_timeout(2000)

            # =========================
            # メニュー確定
            # =========================
            print("🟢 確定")

            page.get_by_role("button", name=re.compile("確定")).first.click(force=True)
            page.wait_for_timeout(7000)

            # =========================
            # カレンダー確認
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
            page.screenshot(path="error.png", full_page=True)

        finally:
            browser.close()

    # =========================
    # 整形
    # =========================

    all_found = list(dict.fromkeys(all_found))

    print("📦 final:", len(all_found))

    # =========================
    # 差分
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
    # 通知
    # =========================

    msg = ["🟢 Akai IPL監視"]

    if not is_changed:
        msg.append("（前回から変更なし）")

    if not all_found:
        msg.append("\n空きなし")

    else:
        msg.append("")
        for x in all_found:
            msg.append("・" + x)

    send_discord("\n".join(msg))

    print("✅ done")


if __name__ == "__main__":
    run()
