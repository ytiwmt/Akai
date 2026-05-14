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
        url = (
            REDIS_URL.replace("redis://", "rediss://", 1)
            if REDIS_URL.startswith("redis://")
            else REDIS_URL
        )

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
        requests.post(
            WEBHOOK_URL,
            json={"content": msg + "\n\u200b\n"},
            timeout=10
        )
    except Exception as e:
        print("Discord error:", e)

# =========================
# カレンダー出現待ち
# =========================

def wait_calendar(page):

    for _ in range(15):

        if page.locator("text=翌週").count() > 0:
            print("📅 カレンダー表示確認")
            return True

        time.sleep(1)

    return False

# =========================
# カテゴリ展開
# =========================

def open_category(page):

    print("🟢 カテゴリ展開")

    page.get_by_text(
        "当日施術のみ",
        exact=False
    ).click(force=True)

    page.wait_for_timeout(2000)

# =========================
# IPL選択
# =========================

def select_ipl(page):

    print("🟢 IPL選択")

    page.locator("label").filter(
        has_text="IPL"
    ).first.click(force=True)

    page.wait_for_timeout(1000)

# =========================
# 確定
# =========================

def confirm_menu(page):

    print("🟢 メニュー確定")

    btn = page.get_by_role(
        "button",
        name=re.compile("確定")
    )

    btn.first.click(force=True)

    page.wait_for_timeout(7000)

    return wait_calendar(page)

# =========================
# 翌週
# =========================

def click_next(page):

    btn = page.locator("button:has-text('翌週')").first

    if btn.count() == 0:
        print("⛔ 翌週なし")
        return False

    btn.scroll_into_view_if_needed()
    btn.click(force=True)

    time.sleep(4)

    return True

# =========================
# ◎取得
# =========================

def scan(page):

    found = []

    elems = page.locator("text=◎, text=△")

    for i in range(elems.count()):
        try:
            found.append(elems.nth(i).inner_text().strip())
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
            args=["--no-sandbox"]
        )

        page = browser.new_page()

        try:

            print("🚀 open")

            page.goto(URL, timeout=60000, wait_until="networkidle")

            page.wait_for_timeout(5000)

            # =========================
            # 再診
            # =========================

            page.locator('[data-id="operation-selection"]') \
                .filter(has_text="再診") \
                .click(force=True)

            page.wait_for_timeout(2000)

            # =========================
            # 予約に進む
            # =========================

            page.get_by_role("button", name=re.compile("予約")) \
                .click(force=True)

            page.wait_for_timeout(5000)

            # =========================
            # ★重要：カテゴリ展開
            # =========================

            open_category(page)

            # =========================
            # IPL
            # =========================

            select_ipl(page)

            # =========================
            # 確定
            # =========================

            ok = confirm_menu(page)

            if not ok:
                print("❌ カレンダー未到達")
                return

            # =========================
            # 3週間取得
            # =========================

            for w in range(3):

                print(f"week {w}")

                all_found.extend(scan(page))

                if w == 2:
                    break

                if not click_next(page):
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

    msg = ["🟢 Akai IPL監視"]

    if not is_changed:
        msg.append("（前回から変更なし）")

    if not all_found:
        msg.append("")
        msg.append("空きなし")

    else:
        msg.append("")
        for x in all_found:
            msg.append("・" + x)

    send_discord("\n".join(msg))

    print("✅ done")


if __name__ == "__main__":
    run()
