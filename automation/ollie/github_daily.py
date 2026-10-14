"""Run the KPI digest in GitHub Actions without a continuously running bot.

The state branch contains only authenticated encrypted SQLite bytes. Secrets,
Trainer identities, message bodies and receipts never enter Actions logs.
"""

import argparse
import asyncio
import base64
import gzip
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time

import requests

from kpi import SupabaseKpiSource, KpiSourceError
from kpi_scheduler import KpiBridge
from deadline_scheduler import configure_deadline_policy, sync_deadlines
from tracker import Tracker, DingTalkSender, DeliveryError, VIETNAM, local_time


class StateError(Exception):
    pass


class GitHubState:
    branch = "ollie-kpi-state"
    filename = "kpi-state.enc"

    def __init__(self, repository, token, master_key, base_sha, session=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise StateError("invalid_repository")
        if not token or not re.fullmatch(r"[a-f0-9]{40}", base_sha):
            raise StateError("missing_github_credentials")
        try:
            self.key = base64.b64decode(master_key, validate=True)
        except (ValueError, TypeError):
            raise StateError("invalid_ledger_key") from None
        if len(self.key) != 32:
            raise StateError("invalid_ledger_key")
        self.base = f"https://api.github.com/repos/{repository}"
        self.aad = f"{repository}:{self.branch}:{self.filename}:v1".encode()
        self.base_sha = base_sha
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": "Bearer " + token,
                                  "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28"})
        self.sha = None

    def request(self, method, path, **kwargs):
        try:
            response = self.http.request(method, self.base + path, timeout=25, **kwargs)
        except requests.RequestException:
            raise StateError("github_state_connection_failed") from None
        if response.status_code == 404 and method == "GET":
            return None
        if not response.ok:
            raise StateError(f"github_state_http_{response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise StateError("github_state_invalid_response") from None

    def encrypt(self, data):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        return b"OLLIE1" + nonce + AESGCM(self.key).encrypt(nonce, gzip.compress(data), self.aad)

    def decrypt(self, data):
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        if not data.startswith(b"OLLIE1") or len(data) < 34:
            raise StateError("invalid_ledger_envelope")
        try:
            compressed = AESGCM(self.key).decrypt(data[6:18], data[18:], self.aad)
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                plain = stream.read(5_000_001)
        except (InvalidTag, OSError, EOFError):
            raise StateError("ledger_integrity_failed") from None
        if len(plain) > 5_000_000 or not plain.startswith(b"SQLite format 3\x00"):
            raise StateError("invalid_ledger_database")
        return plain

    def restore(self, destination):
        value = self.request("GET", f"/contents/{self.filename}", params={"ref": self.branch})
        if value is None:
            # A 404 is initial setup only if the state branch itself is absent.
            # An existing branch with a missing ledger must not silently reset sends.
            if self.request("GET", f"/git/ref/heads/{self.branch}") is not None:
                raise StateError("existing_ledger_missing")
            return False
        if value.get("encoding") != "base64" or not value.get("sha"):
            raise StateError("invalid_ledger_response")
        try:
            encrypted = base64.b64decode(value["content"])
        except (KeyError, ValueError):
            raise StateError("invalid_ledger_response") from None
        Path(destination).write_bytes(self.decrypt(encrypted))
        Path(destination).chmod(0o600)
        self.sha = value["sha"]
        return True

    def save(self, database):
        if self.sha is None and self.request("GET", f"/git/ref/heads/{self.branch}") is None:
            self.request("POST", "/git/refs", json={"ref": "refs/heads/" + self.branch,
                                                   "sha": self.base_sha})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            copy = sqlite3.connect(path)
            try:
                database.backup(copy)
            finally:
                copy.close()
            encrypted = self.encrypt(path.read_bytes())
        payload = {"message": "Save encrypted Ollie KPI delivery state",
                   "branch": self.branch,
                   "content": base64.b64encode(encrypted).decode()}
        if self.sha:
            payload["sha"] = self.sha
        response = self.request("PUT", f"/contents/{self.filename}", json=payload)
        try:
            self.sha = response["content"]["sha"]
        except (KeyError, TypeError):
            raise StateError("ledger_save_unconfirmed") from None


def validate_configuration(config):
    source, settings, state = config["source"], config["settings"], config["state"]
    mapping = settings["trainer_recipients"]
    if not mapping or any(v.get("channel") != "dm" or not v.get("target") for v in mapping.values()):
        raise StateError("numeric_trainer_accounts_required")
    if len({v["target"] for v in mapping.values()}) != len(mapping):
        raise StateError("duplicate_trainer_account")
    if settings["hour"] != 8 or settings["minute"] != 0 or settings.get("timezone") != "Asia/Ho_Chi_Minh":
        raise StateError("unexpected_schedule")
    if not state.get("leader_staff_id") or not state.get("conversation_id"):
        raise StateError("missing_leader_or_group")
    if config["credentials"]["appKey"] != state["robot_code"]:
        raise StateError("credentials_mismatch")
    SupabaseKpiSource(source)


def deliver_jobs(tracker, sender, store, now):
    accepted = failed = uncertain = 0
    # A daily cycle includes KPI and deadline digests (up to 30 destinations).
    # Drain successive bounded batches instead of stopping after the first 20.
    for _ in range(10):
        batch = tracker.next_jobs(now)
        if not batch: break
        result = deliver_batch(tracker, sender, store, now, batch)
        accepted += result['accepted']; failed += result['failed']; uncertain += result['uncertain']
    return {"accepted": accepted, "failed": failed, "uncertain": uncertain}


def deliver_batch(tracker, sender, store, now, jobs):
    accepted = failed = uncertain = 0
    for job in jobs:
        content = tracker.job_content(job, now)
        if not content:
            tracker.finish_job(job[0], "skipped", now)
            store.save(tracker.db)
            continue
        if not tracker.begin_job(job[0], now):
            continue
        # Persist 'sending' before contacting DingTalk. If a runner disappears,
        # Tracker converts it to 'unknown' instead of automatically duplicating it.
        store.save(tracker.db)
        try:
            receipt = sender.send(job[3], job[4], content)
        except DeliveryError as error:
            status = "unknown" if error.ambiguous else "retry"
            tracker.finish_job(job[0], status, time.time(), error=error.code)
            uncertain += int(error.ambiguous)
            failed += int(not error.ambiguous)
        except Exception:
            tracker.finish_job(job[0], "unknown", time.time(), error="unexpected_send_result")
            uncertain += 1
        else:
            tracker.finish_job(job[0], "accepted", time.time(), receipt=receipt)
            accepted += 1
        store.save(tracker.db)
    return {"accepted": accepted, "failed": failed, "uncertain": uncertain}


async def run(config, send=False, morning_catchup=False):
    validate_configuration(config)
    now = time.time()
    if morning_catchup:
        if not send:
            raise StateError('morning_catchup_requires_send')
        # The group-history workflow also runs at night. It may recover a
        # missed morning digest, but must not send next day's KPI before 08:00.
        if not 8 <= local_time(now).hour < 12:
            print(json.dumps({'mode': 'morning_catchup_not_due', 'messages_sent': 0}))
            return
    if not send:
        snapshot = await asyncio.to_thread(SupabaseKpiSource(config["source"]).snapshot,
                                          local_time(now).strftime("%Y-%m"))
        reports = snapshot.reports()
        if not reports or any(r["trainer_id"] not in config["settings"]["trainer_recipients"] for r in reports):
            raise KpiSourceError("trainer_mapping_incomplete")
        # Verify that this runner can authenticate the configured DingTalk bot.
        # Do not print or persist the returned access token or send any message.
        await asyncio.to_thread(DingTalkSender(config["credentials"], config["state"]).access_token)
        database = sqlite3.connect(':memory:')
        try:
            tracker = Tracker(database, config['state'])
            configure_deadline_policy(tracker)
            deadline_counts = await sync_deadlines(tracker, config, now)
        finally:
            database.close()
        print(json.dumps({"mode": "verify_only", "trainer_reports": len(reports),
                          "dingtalk_auth_verified": True, "messages_sent": 0,
                          'deadline_source_verified': True, **deadline_counts}))
        return
    if not config["settings"].get("enabled"):
        print(json.dumps({"mode": "disabled", "messages_sent": 0}))
        return
    store = GitHubState(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", ""),
                        config.get("ledger_key") or os.environ.get("OLLIE_LEDGER_KEY", ""), os.environ.get("GITHUB_SHA", ""))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        database_path = root / "kpi.sqlite3"
        store.restore(database_path)
        database = sqlite3.connect(database_path)
        try:
            tracker = Tracker(database, config["state"])
            configure_deadline_policy(tracker)
            (root / "source.json").write_text(json.dumps(config["source"]))
            (root / "settings.json").write_text(json.dumps(config["settings"]))
            bridge = KpiBridge(database, config["state"], root)
            source_errors = []
            try:
                await sync_deadlines(tracker, config, now)
                tracker.prepare_jobs(now)
            except KpiSourceError as error:
                source_errors.append(str(error))
            try:
                await bridge.prepare(now)
            except KpiSourceError as error:
                source_errors.append(str(error))
            database.execute("DELETE FROM kpi_messages WHERE day < date(?, '-7 days')", (local_time(now).date().isoformat(),))
            database.execute("DELETE FROM outbox WHERE kind='kpi' AND reference NOT IN (SELECT reference FROM kpi_messages)")
            database.execute("DELETE FROM kpi_runs WHERE day < date(?, '-7 days')", (local_time(now).date().isoformat(),))
            database.commit()
            store.save(database)
            result = deliver_jobs(tracker, DingTalkSender(config["credentials"], config["state"]), store, now)
            outstanding = database.execute("""SELECT COUNT(*) FROM outbox o
                LEFT JOIN kpi_messages m ON m.reference=o.reference
                WHERE ((o.kind='kpi' AND m.day=?) OR (o.kind='daily' AND o.reference=?))
                AND o.status NOT IN ('accepted','skipped')""",
                (local_time(now).date().isoformat(), local_time(now).date().isoformat())).fetchone()[0]
            print(json.dumps({"mode": "send", **result, "outstanding": outstanding}))
            if outstanding or result["failed"] or result["uncertain"]:
                raise StateError("delivery_needs_review")
            if source_errors:
                raise KpiSourceError(source_errors[0])
        finally:
            database.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Send the daily digest; default only verifies the data")
    parser.add_argument('--morning-catchup', action='store_true',
                        help='With --send, recover missing reports only between 08:00 and 12:00 Vietnam')
    args = parser.parse_args()
    try:
        raw = os.environ.get("OLLIE_KPI_CONFIG_JSON", "")
        if not raw.strip():
            raise StateError("repository_secret_missing")
        try:
            config = json.loads(raw)
        except json.JSONDecodeError:
            raise StateError("repository_secret_invalid_json") from None
        if not isinstance(config, dict) or any(k not in config for k in ("source", "settings", "state", "credentials")):
            raise StateError("repository_secret_incomplete")
        asyncio.run(run(config, args.send, args.morning_catchup))
    except (KpiSourceError, StateError, DeliveryError) as error:
        print("Ollie KPI: " + str(error))
        return 1
    except Exception as error:
        # Class and source location diagnose failures without printing secret
        # values, HTTP response bodies, local variables or exception messages.
        print("Ollie KPI: runtime_" + type(error).__name__)
        import traceback
        frames = traceback.extract_tb(error.__traceback__)
        if frames:
            frame = frames[-1]
            print(f"Failure location: {Path(frame.filename).name}:{frame.lineno} ({frame.name})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
