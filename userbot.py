"""
userbot.py — Telethon client manager + forwarding engine
Python 3.9+ compatible
"""
import asyncio
import logging
from typing import Callable, Optional

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    UserBannedInChannelError,
    ChatWriteForbiddenError,
    PeerFloodError,
)
from telethon.tl.types import Channel, Chat

import storage
from config import SESSIONS_DIR

logger = logging.getLogger(__name__)

# ─── Runtime state ───────────────────────────────────────────────────────────
_clients   = {}   # acc_id → TelegramClient
_fwd_tasks = {}   # acc_id → asyncio.Task
_fwd_active = {}  # acc_id → bool
_fwd_stats  = {}  # acc_id → dict
_pending    = {}  # phone  → pending session dict


# ─── Startup: reconnect saved accounts ───────────────────────────────────────

async def start_existing_clients():
    accounts = storage.get_accounts()
    for acc_id, acc in accounts.items():
        try:
            client = TelegramClient(
                acc["session_file"], int(acc["api_id"]), acc["api_hash"],
                connection_retries=5, retry_delay=3,
            )
            await client.connect()
            if await client.is_user_authorized():
                _clients[acc_id] = client
                logger.info(f"✅ Reconnected: {acc['phone']} ({acc_id})")
            else:
                logger.warning(f"⚠️  Session expired for {acc['phone']}")
                await client.disconnect()
        except Exception as e:
            logger.error(f"❌ Could not start client {acc_id}: {e}")


# ─── Add account (OTP flow) ───────────────────────────────────────────────────

async def begin_add_account(phone, api_id, api_hash):
    session_file = str(SESSIONS_DIR / f"{phone.replace('+','').replace(' ','')}.session")
    client = TelegramClient(session_file, int(api_id), api_hash,
                            connection_retries=5, retry_delay=2)
    await client.connect()
    result = await client.send_code_request(phone)
    _pending[phone] = {
        "client": client,
        "phone_code_hash": result.phone_code_hash,
        "api_id": api_id,
        "api_hash": api_hash,
        "session_file": session_file,
    }


async def complete_add_account(phone, code):
    p = _pending.get(phone)
    if not p:
        raise ValueError("No pending session for this phone. Start over.")
    try:
        await p["client"].sign_in(phone, code, phone_code_hash=p["phone_code_hash"])
    except PhoneCodeInvalidError:
        raise ValueError("❌ Wrong OTP code. Try again.")
    except PhoneCodeExpiredError:
        raise ValueError("❌ OTP expired. Use /cancel and start over.")
    except SessionPasswordNeededError:
        raise
    return await _save_pending(phone)


async def complete_add_account_2fa(phone, password):
    p = _pending.get(phone)
    if not p:
        raise ValueError("No pending session.")
    await p["client"].sign_in(password=password)
    return await _save_pending(phone)


async def _save_pending(phone):
    p = _pending.pop(phone)
    acc_id = storage.add_account(
        phone=phone,
        api_id=p["api_id"],
        api_hash=p["api_hash"],
        session_file=p["session_file"],
    )
    _clients[acc_id] = p["client"]
    return acc_id


# ─── Group fetching ───────────────────────────────────────────────────────────

async def get_all_groups(acc_id):
    client = _clients.get(acc_id)
    if not client:
        return []
    groups = []
    try:
        async for dialog in client.iter_dialogs():
            ent = dialog.entity
            if isinstance(ent, Chat):
                groups.append(dialog)
            elif isinstance(ent, Channel) and ent.megagroup:
                groups.append(dialog)
    except Exception as e:
        logger.error(f"get_all_groups [{acc_id}]: {e}")
    return groups


# ─── Forwarding engine ────────────────────────────────────────────────────────

async def _forward_loop(acc_id, message_text, delay, notify_cb=None):
    client = _clients.get(acc_id)
    if not client:
        logger.error(f"No client for {acc_id}")
        return

    accounts   = storage.get_accounts()
    phone      = accounts.get(acc_id, {}).get("phone", acc_id)
    loop_count = 0
    _fwd_stats[acc_id] = {"sent": 0, "errors": 0, "loops": 0}
    logger.info(f"▶️  Forward loop started: {phone}")

    try:
        while _fwd_active.get(acc_id, False):
            groups = await get_all_groups(acc_id)
            if not groups:
                logger.warning(f"[{phone}] No groups found — retrying in {delay}s")
                await asyncio.sleep(delay)
                continue

            loop_count += 1
            _fwd_stats[acc_id]["loops"] = loop_count
            logger.info(f"[{phone}] Loop #{loop_count} — {len(groups)} groups")

            for idx, dialog in enumerate(groups):
                if not _fwd_active.get(acc_id, False):
                    break
                try:
                    await client.send_message(dialog.entity, message_text)
                    _fwd_stats[acc_id]["sent"] += 1
                    logger.info(f"[{phone}] ✅ Sent → {dialog.name}")
                except FloodWaitError as e:
                    wait = e.seconds + 10
                    logger.warning(f"[{phone}] FloodWait {wait}s")
                    await asyncio.sleep(wait)
                    continue
                except (UserBannedInChannelError, ChatWriteForbiddenError):
                    logger.warning(f"[{phone}] No permission in {dialog.name}")
                except PeerFloodError:
                    logger.warning(f"[{phone}] PeerFlood — sleeping 60s")
                    await asyncio.sleep(60)
                except Exception as e:
                    _fwd_stats[acc_id]["errors"] += 1
                    logger.error(f"[{phone}] Error in {dialog.name}: {e}")

                if idx < len(groups) - 1 and _fwd_active.get(acc_id, False):
                    await asyncio.sleep(delay)

    except asyncio.CancelledError:
        logger.info(f"⏹  Forward loop cancelled: {phone}")
    except Exception as e:
        logger.error(f"[{phone}] Fatal loop error: {e}")
    finally:
        _fwd_active[acc_id] = False
        logger.info(f"[{phone}] Loop ended. Stats: {_fwd_stats.get(acc_id)}")


def start_forwarding(acc_id, message_text, delay):
    if _fwd_active.get(acc_id) and acc_id in _fwd_tasks and not _fwd_tasks[acc_id].done():
        return False
    _fwd_active[acc_id] = True
    task = asyncio.create_task(_forward_loop(acc_id, message_text, delay))
    _fwd_tasks[acc_id] = task
    return True


def stop_forwarding(acc_id):
    _fwd_active[acc_id] = False
    task = _fwd_tasks.pop(acc_id, None)
    if task and not task.done():
        task.cancel()


def stop_all_forwarding():
    active = list(get_active_forwarders())
    for acc_id in active:
        stop_forwarding(acc_id)
    return len(active)


# ─── Status helpers ───────────────────────────────────────────────────────────

def is_client_connected(acc_id):
    c = _clients.get(acc_id)
    return c is not None and c.is_connected()

def is_forwarding(acc_id):
    return bool(_fwd_active.get(acc_id)) and acc_id in _fwd_tasks and not _fwd_tasks[acc_id].done()

def get_active_forwarders():
    return [aid for aid in _fwd_active if is_forwarding(aid)]

def get_stats(acc_id):
    return _fwd_stats.get(acc_id, {"sent": 0, "errors": 0, "loops": 0})

async def disconnect_account(acc_id):
    stop_forwarding(acc_id)
    client = _clients.pop(acc_id, None)
    if client:
        await client.disconnect()
