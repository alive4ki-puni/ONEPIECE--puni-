"""
翌日の投稿プレビューをDiscordに送信するスクリプト
毎晩22時にGitHub Actionsから実行される
"""
import os
import json
import requests
from datetime import date, timedelta
from pathlib import Path

def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def get_tomorrow_posts():
    tomorrow = date.today() + timedelta(days=1)
    year, week, _ = tomorrow.isocalendar()
    drafts_path = Path(__file__).parent.parent / "operation" / "posts" / "weekly_drafts_{0}W{1:02d}.md".format(year, week)

    if not drafts_path.exists():
        return None, None

    content = drafts_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    date_pattern = "{}/{}".format(tomorrow.month, tomorrow.day)

    # 明日のセクションを探す
    date_line_idx = -1
    for i, line in enumerate(lines):
        if date_pattern in line and "═" not in line:
            date_line_idx = i
            break

    if date_line_idx == -1:
        return tomorrow, None

    # 翌日のセクション終端
    next_date_idx = len(lines)
    for i in range(date_line_idx + 1, len(lines)):
        line = lines[i]
        if line.startswith("## ") and "/" in line and "═" not in line and date_pattern not in line:
            next_date_idx = i
            break

    # 各スロットのタイトルだけ抽出
    slot_titles = []
    slot_keywords = ["朝7時", "昼12時", "夜21時"]
    for i in range(date_line_idx, next_date_idx):
        line = lines[i]
        if line.startswith("###"):
            for kw in slot_keywords:
                if kw in line:
                    title = line.replace("###", "").strip()
                    slot_titles.append(title)

    # 各スロットの1投稿目だけ抽出
    previews = []
    slot_indices = []
    for i in range(date_line_idx, next_date_idx):
        if lines[i].startswith("###"):
            slot_indices.append(i)

    for idx in slot_indices:
        slot_end = next_date_idx
        for j in range(idx + 1, next_date_idx):
            if lines[j].startswith("###"):
                slot_end = j
                break
        slot_block = "\n".join(lines[idx:slot_end])
        marker = "【1/4】"
        start = slot_block.find(marker)
        if start != -1:
            start += len(marker)
            end = slot_block.find("【2/4】", start)
            if end == -1:
                end = start + 200
            preview = slot_block[start:end].strip()[:150]
            previews.append(preview)

    return tomorrow, list(zip(slot_titles, previews))


def send_to_discord(tomorrow, slots, webhook_url, approve_url):
    date_str = "{}月{}日".format(tomorrow.month, tomorrow.day)

    embeds = []
    slot_emojis = ["🌅 朝7時", "☀️ 昼12時", "🌙 夜21時"]

    for i, (title, preview) in enumerate(slots):
        emoji = slot_emojis[i] if i < len(slot_emojis) else ""
        embeds.append({
            "title": "{} {}".format(emoji, title),
            "description": preview + "...",
            "color": 0xF4A460
        })

    message = {
        "content": "**明日({})の投稿プレビュー**\n内容を確認して承認してください👇\n\n✅ 承認する：{}".format(date_str, approve_url),
        "embeds": embeds
    }

    resp = requests.post(webhook_url, json=message)
    resp.raise_for_status()
    print("[INFO] Discordにプレビューを送信しました")


def main():
    load_env()

    discord_url = os.environ.get("DISCORD_WEBHOOK_URL")
    make_url = os.environ.get("MAKE_WEBHOOK_URL")

    if not discord_url:
        print("[ERROR] DISCORD_WEBHOOK_URL が未設定です")
        return

    tomorrow, slots = get_tomorrow_posts()

    if not slots:
        print("[ERROR] 明日({})の投稿データが見つかりません".format(tomorrow))
        return

    # 承認URLにはMake WebhookのURLを使用
    approve_url = "{}?date={}&approved=true".format(make_url, tomorrow.isoformat()) if make_url else "（未設定）"

    send_to_discord(tomorrow, slots, discord_url, approve_url)


if __name__ == "__main__":
    main()
