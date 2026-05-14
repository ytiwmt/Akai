import os
import re
import json
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

    tables = page.locator("table")

    table_count = tables.count()

    print(f"📊 table count: {table_count}")

    for t_idx in range(table_count):

        table = tables.nth(t_idx)

        try:

            table_text = table.inner_text()

            # 空き記号を含むtableだけ対象
            if not any(x in table_text for x in ["◎", "×", "－"]):
                continue

            print(f"✅ target table: {t_idx}")

            rows = table.locator("tr")

            for r_idx in range(rows.count()):

                row = rows.nth(r_idx)

                text = " ".join(
                    row.inner_text().split()
                )

                # 日付行だけ抽出
                if re.search(r"\d+/\d+", text):

                    found.append(text)

        except Exception as e:

            print("❌ table parse error:", e)

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

            # =========================
            # Open
            # =========================

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

            page.wait_for_timeout(2000)

            # =========================
            # 予約に進む
            # =========================

            print("🟢 Click 予約に進む")

            page.get_by_role(
                "button",
                name="予約に進む"
            ).click()

            page.wait_for_timeout(4000)

            # =========================
            # IPL選択
            # =========================

            print("🟢 Select IPL")

            page.get_by_text("IPL").click()

            page.wait_for_timeout(2000)

            # =========================
            # メニューを確定
            # =========================

            print("🟢 Click メニューを確定する")

            page.get_by_role(
                "button",
                name="メニューを確定する"
            ).click()

            page.wait_for_timeout(5000)

            # =========================
            # カレンダー待機
            # =========================

            page.wait_for_selector(
                "table",
                timeout=60000
            )

            page.wait_for_timeout(5000)

            # =========================
            # デバッグ
            # =========================

            print("========== BODY DEBUG ==========")

            try:

                body_text = page.locator("body").inner_text()

                print(body_text[:5000])

            except Exception as e:

                print("❌ body debug error:", e)

            print("================================")

            # =========================
            # 3週間分取得
            # =========================

            for week in range(3):

                print(f"📅 week {week}")

                result = scan_slots(page)

                print(f"found count: {len(result)}")

                all_found.extend(result)

                # 最後の週は押さない
                if week == 2:
                    break

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

                print("➡ click next week")

                next_btn.click()

                page.wait_for_timeout(4000)

        except Exception as e:

            print("❌ Error:", e)

        finally:

            browser.close()

    # =========================
    # 重複除去（順番維持）
    # =========================

    all_found = list(dict.fromkeys(all_found))

    print(f"📦 final rows: {len(all_found)}")

    # =========================
    # 差分検知
    # =========================

    is_changed = True

    if r:

        try:

            last_raw = r.get(REDIS_KEY)

            if last_raw:

                last_data = json.loads(last_raw)

                if set(last_data) == set(all_found):

                    is_changed = False

            r.set(
                REDIS_KEY,
                json.dumps(all_found)
            )

        except Exception as e:

            print("❌ Redis compare error:", e)

    # =========================
    # 月別整理
    # =========================

    grouped = {}

    for line in all_found:

        match = re.search(r"(\d+)/", line)

        if not match:
            continue

        month = int(match.group(1))

        if month not in grouped:
            grouped[month] = []

        grouped[month].append(line)

    # =========================
    # メッセージ生成
    # =========================

    lines = []

    lines.append("🟢 Akai IPL監視")

    if not is_changed:

        lines.append("（前回から変更なし）")

    if not all_found:

        lines.append("")
        lines.append("⚠ 抽出失敗 or 空きなし")

    else:

        for month in sorted(grouped.keys()):

            lines.append("")
            lines.append(f"【{month}月】")

            for line in grouped[month]:

                if "◎" in line:

                    lines.append(f"🚨 {line}")

                else:

                    lines.append(line)

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
