"""
Threads投稿スクリプト
環境変数: THREADS_ACCESS_TOKEN, THREADS_USER_ID, GITHUB_TOKEN, GITHUB_REPO
引数: --slot (SLOT_1=7時 / SLOT_2=12時 / SLOT_3=21時)
      --skip-approval: 承認チェックをスキップ
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

def check_approval():
    """今日の承認IssueがGitHubに存在するか確認する"""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")

    if not token or not repo:
        print("[WARN] GITHUB_TOKEN または GITHUB_REPO が未設定のため承認チェックをスキップします")
        return True

    today = date.today().isoformat()
    url = "https://api.github.com/repos/{}/issues".format(repo)
    headers = {"Authorization": "token {}".format(token)}
    params = {"state": "open", "per_page": 20}

    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        print("[WARN] GitHub APIエラー。承認チェックをスキップします")
        return True

    issues = resp.json()
    for issue in issues:
        title = issue.get("title", "")
        created = issue.get("created_at", "")[:10]
        if "approved" in title.lower() and created == today:
            print("[INFO] 承認確認OK (Issue: {})".format(title))
            return True

    print("[ERROR] 本日({})の承認Issueが見つかりません".format(today))
    print("[ERROR] Discordの承認リンクをタップしてから再実行してください")
    return False

def get_today_post(slot):
    today = date.today()
    year, week, _ = today.isocalendar()
    drafts_path = Path(__file__).parent.parent / "operation" / "posts" / "weekly_drafts_{0}W{1:02d}.md".format(year, week)

    if not drafts_path.exists():
        print("[ERROR] 下書きファイルが見つかりません: {}".format(drafts_path))
        return None

    content = drafts_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    slot_keyword = {"SLOT_1": "朝7時", "SLOT_2": "昼12時", "SLOT_3": "夜21時"}.get(slot)
    slot_time = {"SLOT_1": "7時", "SLOT_2": "12時", "SLOT_3": "21時"}.get(slot)
    if not slot_keyword:
        print("[ERROR] 不明なスロット: {}".format(slot))
        return None

    date_pattern = "{}/{}".format(today.month, today.day)

    date_line_idx = -1
    for i, line in enumerate(lines):
        if date_pattern in line and "═" not in line:
            date_line_idx = i
            break

    if date_line_idx == -1:
        print("[ERROR] {} のセクションが見つかりません".format(date_pattern))
        return None

    next_date_idx = len(lines)
    for i in range(date_line_idx + 1, len(lines)):
        line = lines[i]
        if line.startswith("## ") and "/" in line and "═" not in line and date_pattern not in line:
            next_date_idx = i
            break

    slot_start = -1
    for i in range(date_line_idx, next_date_idx):
        if lines[i].startswith("###") and slot_keyword in lines[i]:
            slot_start = i
            break

    if slot_start == -1:
        print("[ERROR] {} の {} ブロックが見つかりません".format(date_pattern, slot_keyword))
        return None

    slot_end = next_date_idx
    for i in range(slot_start + 1, next_date_idx):
        if lines[i].startswith("###"):
            slot_end = i
            break

    slot_block = "\n".join(lines[slot_start:slot_end])

    posts = []
    total = 4
    for i in range(1, total + 1):
        marker = "【{}/{}】".format(i, total)
        start = slot_block.find(marker)
        if start == -1:
            continue
        start += len(marker)

        next_marker = "【{}/{}】".format(i + 1, total)
        end = slot_block.find(next_marker, start)
        if end == -1:
            end = len(slot_block)

        post_text = slot_block[start:end].strip()
        if "\n---" in post_text:
            post_text = post_text[:post_text.index("\n---")].strip()

        if post_text:
            posts.append(post_text)

    if not posts:
        print("[ERROR] 投稿テキストが解析できませんでした")
        return None

    return ("{} {}".format(date_pattern, slot_time), posts)


def create_thread_container(user_id, token, text, reply_to_id=None):
    url = "{}/{}/threads".format(BASE_URL, user_id)
    params = {"media_type": "TEXT", "text": text, "access_token": token}
    if reply_to_id:
        params["reply_to_id"] = reply_to_id
    resp = requests.post(url, data=params)
    resp.raise_for_status()
    return resp.json()["id"]


def publish_container(user_id, token, container_id):
    url = "{}/{}/threads_publish".format(BASE_URL, user_id)
    params = {"creation_id": container_id, "access_token": token}
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
    parser.add_argument("--skip-approval", action="store_true", dest="skip_approval")
    args = parser.parse_args()

    # 承認チェック
    if not args.skip_approval and not args.dry_run:
        if not check_approval():
            sys.exit(1)

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
