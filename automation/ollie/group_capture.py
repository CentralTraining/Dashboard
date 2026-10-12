"""Read only the leader's notices from the configured DingTalk group."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
from types import SimpleNamespace

from announcements import has_deadline, parse_announcement
from deadline_scheduler import configure_deadline_policy, sync_deadlines
from deadline_source import DeadlineSource
from github_daily import GitHubState, StateError, validate_configuration
from tracker import Tracker

AUTH_TABLE = """CREATE TABLE IF NOT EXISTS group_auth (
    profile TEXT PRIMARY KEY, bundle BLOB NOT NULL, cursor REAL NOT NULL)"""


def message_time(value):
    # The pinned CLI's chat_messages.go formats unzoned timestamps in CST,
    # explicitly time.FixedZone("CST", 8*60*60), regardless of runner timezone.
    date = datetime.fromisoformat(str(value))
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone(timedelta(hours=8)))
    return date.timestamp()


def validate_history(data, owner, group):
    if not data.get("complete") or data.get("partial") or data.get("hasMore") or data.get("failedCount") or data.get("truncated"):
        raise StateError("group_history_incomplete")
    filtering = data.get("senderFilter", {})
    if filtering.get("status") != "applied" or not filtering.get("applied"):
        raise StateError("group_sender_filter_missing")
    identities = data.get("resolvedFilters", {}).get("senders", [])
    resolved = [item for item in identities if item.get("status") == "resolved"
                and item.get("selected", {}).get("userId") == owner]
    if len(resolved) != 1:
        raise StateError("group_author_unverified")
    selected = resolved[0]["selected"]
    allowed = {selected.get("userId"), selected.get("openDingTalkId")} - {None, ""}
    messages = data.get("messages", [])
    if any(message.get("senderId") not in allowed or message.get("conversationId") != group for message in messages):
        raise StateError("group_message_scope_mismatch")
    return messages


def command(cli, profile, env, args):
    try:
        result = subprocess.run([str(cli), "--profile", profile, "--timeout", "30", *args],
                                env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise StateError("group_cli_timeout") from None
    if result.returncode:
        raise StateError("group_cli_failed")
    return result.stdout


def capture(config, database, root, cli):
    database.execute(AUTH_TABLE)
    rows = database.execute("SELECT profile,bundle,cursor FROM group_auth").fetchall()
    if len(rows) != 1:
        raise StateError("group_login_missing")
    profile, bundle, cursor = rows[0]
    owner = config["state"]["leader_staff_id"]
    if not profile.endswith(":" + owner):
        raise StateError("group_login_owner_mismatch")
    auth_file = root / "auth-private.tar.gz"
    auth_file.write_bytes(bundle)
    auth_file.chmod(0o600)
    env = {**os.environ, "DWS_CONFIG_DIR": str(root / "dws-config"),
           "DWS_KEYCHAIN_DIR": str(root / "dws-keychain"), "DWS_LANG": "en"}
    command(cli, profile, env, ["auth", "import", "-i", str(auth_file)])
    now = time.time()
    start = datetime.fromtimestamp(cursor - 300, timezone.utc).isoformat()
    end = datetime.fromtimestamp(now, timezone.utc).isoformat()
    try:
        raw = command(cli, profile, env, ["chat", "+chat-messages", "--group", config["state"]["conversation_id"],
                      "--sender", owner, "--start", start, "--end", end, "--order", "asc",
                      "--page-all", "--page-limit", "20", "--max-items", "1000", "--no-reactions", "-f", "json"])
        messages = validate_history(json.loads(raw), owner, config["state"]["conversation_id"])
        state = {**config["state"], "audience_staff_ids": [value["target"] for value in config["settings"]["trainer_recipients"].values()]}
        tracker = Tracker(database, state)
        configure_deadline_policy(tracker)
        asyncio.run(sync_deadlines(tracker, config, now))
        created = skipped = 0
        for message in sorted(messages, key=lambda item: message_time(item["createTime"])):
            text = message.get("text", "")
            if not has_deadline(text):
                continue
            posted = message_time(message["createTime"])
            try:
                _, deadline = parse_announcement(re.sub(r"@Ollie_MT\b", "", text, flags=re.I).strip(), posted)
            except ValueError:
                skipped += 1
                continue
            if deadline <= now:
                skipped += 1
                continue
            incoming = SimpleNamespace(sender_staff_id=owner, sender_nick=config["state"].get("leader_name", "Nghĩa"),
                         conversation_type="2", conversation_id=config["state"]["conversation_id"],
                         create_at=posted * 1000, original_text=text, at_users=[], chatbot_user_id=config["state"]["robot_code"])
            before = database.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            tracker.handle(text, incoming, message["messageId"], now=posted)
            created += database.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] - before
        source = DeadlineSource(config["source"], config["ledger_key"], config["state"]["conversation_id"])
        for event_id, payload in database.execute("SELECT event_id,payload FROM task_events WHERE synced_at IS NULL").fetchall():
            source.write_event(json.loads(payload))
            database.execute("UPDATE task_events SET synced_at=? WHERE event_id=?", (now, event_id))
        database.execute("UPDATE group_auth SET cursor=? WHERE profile=?", (now, profile))
        database.commit()
        return {"group_history_verified": True, "leader_messages_checked": len(messages),
                "notices_created": created, "notices_skipped": skipped, "messages_sent": 0}
    finally:
        # Persist refreshed login state even if pagination/storage failed.
        refreshed = root / "auth-refreshed-private.tar.gz"
        command(cli, profile, env, ["auth", "export", "-o", str(refreshed)])
        database.execute("UPDATE group_auth SET bundle=? WHERE profile=?", (refreshed.read_bytes(), profile))
        database.commit()


def main():
    os.umask(0o077)
    database = store = None
    try:
        config = json.loads(os.environ["OLLIE_KPI_CONFIG_JSON"])
        validate_configuration(config)
        store = GitHubState(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"],
                            config["ledger_key"], os.environ["GITHUB_SHA"])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "ledger.sqlite3"
            if not store.restore(path):
                raise StateError("group_ledger_missing")
            database = sqlite3.connect(path)
            try:
                result = capture(config, database, root, Path(__file__).resolve().parent / "dws")
            finally:
                store.save(database)
                database.close()
                database = None
            print(json.dumps(result))
        return 0
    except Exception as error:
        print("Ollie group capture: " + (str(error) if isinstance(error, StateError) else type(error).__name__))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
