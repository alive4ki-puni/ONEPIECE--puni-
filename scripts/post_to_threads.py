"""
Threads投稿スクリプト
環境変数: THREADS_ACCESS_TOKEN, THREADS_USER_ID
引数: --slot (SLOT_1=7時 / SLOT_2=12時 / SLOT_3=21時)
"""
import os
import sys
import time
import argparse
import requests
from typing import Optional, List, Tuple
from datetime import date
from pathlib import Path

BASE_URL = "https://graph.threads.net/v1.0"

def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def get_today_post(slot):
    # type: (str) -> Optional[Tuple[str, List[str]]]
    today = date.today()
    year, week, _ = today.isocalendar()
    drafts_path = Path(__file__).parent.parent / "operation" / "posts" / "weekly_drafts_{0}W{1:02d}.md".format(year, week)

    if not drafts_path.exists():
        print("[ERROR] 下書きファイルが見つかりません: {}".format(drafts_path))
        return None

    content = drafts_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # スロット→キーワードマッピング
    slot_keyword = {"SLOT_1": "朝7時", "SLOT_2": "昼12時", "SLOT_3": "夜21時"}.get(slot)
    slot_time = {"SLOT_1": "7時", "SLOT_2": "12時", "SLOT_3": "21時"}.get(slot)
    if not slot_keyword:
        print("[ERROR] 不明なスロット: {}".format(slot))
        return None

    # 今日の日付パターン（例: 4/23）
    date_pattern = "{}/{}".format(today.month, today.day)

    # 今日の日付行を探す（═══行は無視）
    date_line_idx = -1
    for i, line in enumerate(lines):
        if date_pattern in line and "═" not in line:
            date_line_idx = i
            break

    if date_line_idx == -1:
        print("[ERROR] {} のセクションが見つかりません".format(date_pattern))
        print("[DEBUG] ファイル内容の先頭:\n{}".format(content[:300]))
        return None

    # 今日のセクション終端を探す（次の日付行 or ファイル末尾）
    next_date_idx = len(lines)
    for i in range(date_line_idx + 1, len(lines)):
        line = lines[i]
        # 次の日付セクション（例: ## 4/24）
        if line.startswith("## ") and "/" in line and "═" not in line and date_pattern not in line:
            next_date_idx = i
            break

    today_section = "\n".join(lines[date_line_idx:next_date_idx])

    # スロットの ### ヘッダーを探す
    slot_start = -1
    for i, line in enumerate(lines[date_line_idx:next_date_idx], start=date_line_idx):
        if line.startswith("###") and slot_keyword in line:
            slot_start = i
            break

    if slot_start == -1:
        print("[ERROR] {} の {} ブロックが見つかりません".format(date_pattern, slot_keyword))
        print("[DEBUG] today_section:\n{}".format(today_section[:500]))
        return None

    # スロットブロックの終端（次の ### または次の日付）
    slot_end = next_date_idx
    for i in range(slot_start + 1, next_date_idx):
        if lines[i].startswith("###"):
            slot_end = i
            break

    slot_lines = lines[slot_start:slot_end]
    slot_block = "\n".join(slot_lines)

    # 【1/4】〜【4/4】 を分割
    posts = []
    total = 4
    for i in range(1, total + 1):
        marker = "【{}/{}】".format(i, total)
        start = slot_block.find(marker)
        if start == -1:
            continue
        start += len(marker)

        # 次のマーカーまで
        next_marker = "【{}/{}】".format(i + 1, total)
        end = slot_block.find(next_marker, start)
        if end == -1:
            end = len(slot_block)

        post_text = slot_block[start:end].strip()
        # フォローCTAなど末尾の装飾行を除去（「---」以降）
        if "\n---" in post_text:
            post_text = post_text[:post_text.index("\n---")].strip()

        if post_text:
            posts.append(post_text)

    if not posts:
        print("[ERROR] 投稿テキストが解析できませんでした")
        print("[DEBUG] slot_block:\n{}".format(slot_block[:500]))
        return None

    return ("{} {}".format(date_pattern, slot_time), posts)


def create_thread_container(user_id, token, text, reply_to_id=None):
    url = "{}/{}/threads".format(BASE_URL, user_id)
    params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": token,
    }
    if reply_to_id:
        params["reply_to_id"] = reply_to_id

    resp = requests.post(url, data=params)
    resp.raise_for_status()
    return resp.json()["id"]


def publish_container(user_id, token, container_id):
    url = "{}/{}/threads_publish".format(BASE_URL, user_id)
    params = {
        "creation_id": container_id,
        "access_token": token,
    }
    resp = requests.post(url, data=params)
    resp.raise_for_status()
    return resp.json()["id"]


def post_thread_series(posts):
    token = os.environ.get("THREADS_ACCESS_TOKEN")
    user_id = os.environ.get("THREADS_USER_ID")

    if not token or not user_id:
        print("[ERROR] THREADS_ACCESS_TOKEN または THREADS_USER_ID が未設定です")
        sys.exit(1)

    published_ids = []
    reply_to_id = None

    for i, text in enumerate(posts):
        print("[INFO] 投稿{}を作成中...".format(i + 1))
        container_id = create_thread_container(user_id, token, text, reply_to_id)
        print("[INFO] コンテナID: {}".format(container_id))
        time.sleep(2)

        thread_id = publish_container(user_id, token, container_id)
        print("[INFO] 投稿{}完了: {}".format(i + 1, thread_id))
        published_ids.append(thread_id)

        reply_to_id = thread_id
        time.sleep(3)

    return published_ids


def main():
    load_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", required=True, choices=["SLOT_1", "SLOT_2", "SLOT_3"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = get_today_post(args.slot)
    if not result:
        print("[ERROR] 投稿データを取得できませんでした")
        sys.exit(1)

    title, posts = result
    print("[INFO] 投稿対象: {} ({}投稿)".format(title, len(posts)))

    if args.dry_run:
        print("\n=== DRY RUN ===")
        for i, p in enumerate(posts):
            print("\n--- 投稿{} ---\n{}".format(i + 1, p))
        return

    ids = post_thread_series(posts)
    print("\n[SUCCESS] {}件投稿完了: {}".format(len(ids), ids))

    log_path = Path(__file__).parent.parent / "operation" / "posts" / "post_{}.md".format(date.today())
    if not log_path.exists():
        log_path.write_text("# 投稿記録 {}\n\n## {}\n投稿ID: {}\n".format(date.today(), args.slot, ", ".join(ids)))
    else:
        with open(log_path, "a") as f:
            f.write("\n## {}\n投稿ID: {}\n".format(args.slot, ", ".join(ids)))


if __name__ == "__main__":
    main()
