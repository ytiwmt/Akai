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
    if not WEBHOOK_URL:
        print(message)
        return

    try:
        requests.post(
            WEBHOOK_URL,
            json={"content": message + "\n\u200b\n"},
            timeout=10
        )
    except Exception as e:
        print("Discord error:", e)

# =========================
# ◎抽出（DOMベース）
# =========================

def scan_slots(page):

    found = []

    # ◎ or △ のみ拾う（table完全廃止）
    items = page.locator("text=◎, text=△")

    count = items.count()
    print("slot count:", count)

    for i in range(count):
        try:
            txt = items.nth(i).inner_text().strip()
            found.append(txt)
        except:
            pass

    return found

# =========================
# 翌週クリック（安定版）
# =========================

def click_next_week(page):

    btn = page.locator("button:has-text('翌週')").first

    print("next btn count:", btn.count())

    if btn.count() == 0:
        return False

    before_url = page.url

    btn.scroll_into_view_if_needed()
    btn.click(force=True)

    # 重要：URL or DOM変化待ち
    for _ in range(10):
        time.sleep(1)
        if page.url != before_url:
            break

    page.wait_for_timeout(4000)

    return True

# =========================
# メイン
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

            print("🚀 Open page")

            page.goto(URL, timeout=60000, wait_until="networkidle")

            page.wait_for_timeout(6000)

            # =========================
            # 再診
            # =========================

            print("🟢 再診")

            page.locator(
                '[data-id="operation-selection"]'
            ).filter(
                has_text="再診"
            ).click(force=True)

            page.wait_for_timeout(3000)

            # =========================
            # 予約に進む
            # =========================

            print("🟢 予約に進む")

            page.get_by_role("button", name=re.compile("予約")).click(force=True)

            page.wait_for_timeout(5000)

            # =========================
            # IPL（麻酔なし）
            # =========================

            print("🟢 IPL選択")

            page.locator("label").filter(
                has_text="IPL"
            ).filter(
                has_not=page.get_by_text("麻酔あり")
            ).first.click(force=True)

            page.wait_for_timeout(3000)

            # =========================
            # メニュー確定
            # =========================

            print("🟢 メニュー確定")

            page.get_by_role("button", name=re.compile("確定")).click(force=True)

            page.wait_for_timeout(7000)

            # =========================
            # 3週間取得
            # =========================

            for w in range(3):

                print(f"week {w}")

                found = scan_slots(page)
                all_found.extend(found)

                if w == 2:
                    break

                ok = click_next_week(page)

                if not ok:
                    print("⛔ 翌週ボタンなし")
                    break

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
        lines.append("空きなし")

    else:
        lines.append("")
        for x in all_found:
            if "◎" in x:
                lines.append("🚨 " + x)
            else:
                lines.append("・" + x)

    send_discord("\n".join(lines))

    print("✅ done")


if __name__ == "__main__":
    run()
