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

        connection_url = (
            REDIS_URL.replace("redis://", "rediss://", 1)
            if REDIS_URL.startswith("redis://")
            else REDIS_URL
        )

        r = redis.from_url(
            connection_url,
            decode_responses=True,
            ssl_cert_reqs=None
        )

        r.ping()

        print("✅ Redis connected")

    except Exception as e:

        print("❌ Redis error:", e)

        r = None

# =========================
# Discord通知
# =========================

def send_discord(message):

    if not WEBHOOK_URL:

        print(message)

        return

    try:

        requests.post(
            WEBHOOK_URL,
            json={
                "content": message + "\n\u200b\n"
            },
            timeout=10
        )

    except Exception as e:

        print("❌ Discord error:", e)

# =========================
# スキャン
# =========================

def scan_slots(page):

    found = []

    table = page.locator("table")

    rows = table.locator("tr")

    for r_idx in range(rows.count()):

        row = rows.nth(r_idx)

        try:

            text = row.inner_text().strip()

            if "◎" in text:

                cleaned = " ".join(text.split())

                found.append(cleaned)

        except Exception as e:

            print("row parse error:", e)

    return found

# =========================
# メイン
# =========================

def run():

    all_found = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        try:

            print("🚀 Open page")

            page.goto(
                URL,
                timeout=60000
            )

            page.wait_for_timeout(7000)

            # =========================
            # 再診
            # =========================

            print("🟢 Click 再診")

            page.get_by_role(
                "button",
                name=re.compile("再診")
            ).click()

            page.wait_for_timeout(3000)

            # =========================
            # IPL選択
            # =========================

            print("🟢 Select IPL")

            page.get_by_text("IPL").click()

            # =========================
            # カレンダー待機
            # =========================

            page.wait_for_selector("table", timeout=60000)

            page.wait_for_timeout(5000)

            # =========================
            # 週巡回
            # =========================

            for week in range(8):

                print(f"📅 week {week}")

                result = scan_slots(page)

                for x in result:

                    all_found.append(
                        f"[week{week}] {x}"
                    )

                # =========================
                # 翌週
                # =========================

                next_btn = page.get_by_role(
                    "button",
                    name="翌週"
                )

                if next_btn.count() == 0:

                    print("⛔ 翌週ボタンなし")

                    break

                next_btn.click()

                page.wait_for_timeout(4000)

        except Exception as e:

            print("❌ Error:", e)

        finally:

            browser.close()

    # =========================
    # 差分検知
    # =========================

    current_data = sorted(all_found)

    is_changed = True

    if r:

        try:

            last_raw = r.get(REDIS_KEY)

            if last_raw:

                last_data = json.loads(last_raw)

                if set(last_data) == set(current_data):

                    is_changed = False

            r.set(
                REDIS_KEY,
                json.dumps(current_data)
            )

        except Exception as e:

            print("❌ Redis compare error:", e)

    # =========================
    # メッセージ生成
    # =========================

    lines = []

    lines.append("🟢 Akai IPL監視")

    if not all_found:

        lines.append("")
        lines.append("空きなし")

    else:

        lines.append("")

        for x in all_found:

            lines.append(f"・{x}")

    if not is_changed:

        lines.append("")
        lines.append("（前回から変更なし）")

    message = "\n".join(lines)

    # =========================
    # 通知
    # =========================

    send_discord(message)

    print("✅ done")

# =========================
# 実行
# =========================

if __name__ == "__main__":

    run()
