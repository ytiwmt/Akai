import os
import re
import json
import requests
import redis

from playwright.sync_api import sync_playwright

# =========================
# 設定
# =========================

URL = "https://reservation.medical-force.com/c/aa9268a46f2a4da29f4c98b2aee12475"

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
# Discord
# =========================

def send_discord(message):
    print("📨 sending discord")

    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL_Akai missing")
        print(message)
        return

    try:
        res = requests.post(
            WEBHOOK_URL,
            json={"content": message + "\n\u200b\n"},
            timeout=10
        )
        print("📨 discord status:", res.status_code)

    except Exception as e:
        print("❌ Discord error:", e)

# =========================
# スキャン
# =========================

def scan_slots(page):
    found = []

    tables = page.locator("table")
    for t in range(tables.count()):
        table = tables.nth(t)

        try:
            txt = table.inner_text()
            if not any(x in txt for x in ["◎", "×", "－"]):
                continue

            rows = table.locator("tr")

            for i in range(rows.count()):
                row_txt = rows.nth(i).inner_text().strip()

                if re.search(r"\d+/\d+", row_txt):
                    found.append(row_txt)

        except:
            pass

    return found

# =========================
# メイン
# =========================

def run():

    all_found = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

        context = browser.new_context(
            viewport={"width": 1400, "height": 1100},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        try:

            # =========================
            # Open
            # =========================

            print("🚀 Open page")

            page.goto(URL, timeout=60000, wait_until="networkidle")

            page.wait_for_timeout(8000)

            # =========================
            # 再診
            # =========================

            print("🟢 再診クリック")

            page.locator(
                '[data-id="operation-selection"]',
                has_text="再診"
            ).click(force=True)

            page.wait_for_timeout(3000)

            # =========================
            # 予約に進む
            # =========================

            print("🟢 予約に進む")

            page.get_by_role(
                "button",
                name=re.compile("予約")
            ).click(force=True)

            page.wait_for_timeout(5000)

            # =========================
            # IPL（麻酔なし）選択
            # =========================

            print("🟢 IPL選択")

            ipl = page.locator("label").filter(
                has_text="IPL"
            ).filter(
                has_not=page.get_by_text("麻酔あり")
            ).first

            ipl.click(force=True)

            page.wait_for_timeout(3000)

            # =========================
            # メニュー確定
            # =========================

            print("🟢 メニュー確定")

            page.get_by_role(
                "button",
                name=re.compile("確定")
            ).click(force=True)

            page.wait_for_timeout(7000)

            # =========================
            # カレンダー
            # =========================

            print("📅 カレンダー取得")

            page.screenshot(path="calendar.png", full_page=True)

            # =========================
            # 3週間
            # =========================

            for w in range(3):

                print(f"week {w}")

                result = scan_slots(page)

                all_found.extend(result)

                if w == 2:
                    break

                next_btn = page.get_by_role("button", name="翌週")

                if next_btn.count() == 0:
                    break

                next_btn.click(force=True)

                page.wait_for_timeout(4000)

        except Exception as e:

            print("❌ Error:", e)

            try:
                page.screenshot(path="error.png", full_page=True)
            except:
                pass

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
    # メッセージ
    # =========================

    lines = ["🟢 Akai IPL監視"]

    if not is_changed:
        lines.append("（前回から変更なし）")

    if not all_found:
        lines.append("")
        lines.append("空きなし or 取得失敗")

    else:
        lines.append("")
        for x in all_found:
            lines.append("・" + x)

    send_discord("\n".join(lines))

    print("✅ done")


if __name__ == "__main__":
    run()
