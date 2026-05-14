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
# iframe 全探索
# =========================

def get_all_frames(page):
    frames = [page.main_frame] + page.frames
    return frames

# =========================
# ◎抽出（全フレーム対応）
# =========================

def scan_slots(page):

    found = []

    frames = get_all_frames(page)

    for f in frames:

        try:

            # ◎ / △ を直接拾う（table廃止）
            elems = f.locator("text=◎, text=△")

            c = elems.count()

            if c > 0:
                print(f"frame found slots: {c} ({f.url})")

            for i in range(c):
                try:
                    found.append(elems.nth(i).inner_text().strip())
                except:
                    pass

        except:
            pass

    return found

# =========================
# 翌週クリック（全フレーム対応）
# =========================

def click_next_week(page):

    frames = get_all_frames(page)

    for f in frames:

        try:

            btn = f.locator("button:has-text('翌週')").first

            if btn.count() > 0:

                print("➡ next week found in frame:", f.url)

                btn.scroll_into_view_if_needed()
                btn.click(force=True)

                time.sleep(4)

                return True

        except:
            pass

    print("⛔ 翌週ボタン見つからず")
    return False

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

            print("🚀 Open")

            page.goto(URL, timeout=60000, wait_until="networkidle")

            page.wait_for_timeout(8000)

            # =========================
            # 再診
            # =========================

            print("🟢 再診")

            page.locator('[data-id="operation-selection"]') \
                .filter(has_text="再診") \
                .click(force=True)

            page.wait_for_timeout(3000)

            # =========================
            # 予約に進む
            # =========================

            print("🟢 予約")

            page.get_by_role("button", name=re.compile("予約")) \
                .click(force=True)

            page.wait_for_timeout(5000)

            # =========================
            # IPL（麻酔なし）
            # =========================

            print("🟢 IPL")

            page.locator("label").filter(
                has_text="IPL"
            ).filter(
                has_not=page.get_by_text("麻酔あり")
            ).first.click(force=True)

            page.wait_for_timeout(3000)

            # =========================
            # 確定
            # =========================

            print("🟢 確定")

            page.get_by_role("button", name=re.compile("確定")) \
                .click(force=True)

            page.wait_for_timeout(7000)

            # =========================
            # 3週間
            # =========================

            for w in range(3):

                print(f"week {w}")

                found = scan_slots(page)
                all_found.extend(found)

                if w == 2:
                    break

                if not click_next_week(page):
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
    # message
    # =========================

    msg = ["🟢 Akai IPL監視"]

    if not is_changed:
        msg.append("（前回から変更なし）")

    if not all_found:
        msg.append("")
        msg.append("空きなし or 取得失敗")

    else:
        msg.append("")
        for x in all_found:
            msg.append("・" + x)

    send_discord("\n".join(msg))

    print("✅ done")


if __name__ == "__main__":
    run()
