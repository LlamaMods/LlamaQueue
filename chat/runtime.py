import asyncio
import json
import logging
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any

import grpc
import requests
import websockets
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from chat.models import ChatConnection, ChatIdentity
from chat.security import decrypt_token, encrypt_token
from database.session import SessionLocal
from chat.youtube_stream_pb import LiveChatMessageListRequest, LiveChatMessageListResponse

logger = logging.getLogger(__name__)


class ChatHub:
    """Per-process live chat fan-out for dashboard and OBS browser clients."""
    def __init__(self):
        self.messages: dict[int, deque] = {}
        self.clients: dict[int, set] = {}
        self.tasks: dict[tuple[int, str], asyncio.Task] = {}
        self.status: dict[int, dict[str, str]] = {}
        self.youtube_live_chat_ids: dict[int, str] = {}
        self._youtube_lookup_blocked_video: dict[int, str] = {}
        # One YouTube StreamList worker per channel per process. Connected
        # LlamaQueue users for the same channel subscribe to its fan-out.
        self.youtube_channel_subscribers: dict[str, set[int]] = {}
        self.youtube_channel_tasks: dict[str, asyncio.Task] = {}
        # Explicit user-triggered fallback: one quota-metered discovery lookup
        # only when the YouTube backup-connect button is pressed.
        self.youtube_backup_connect_requests: set[str] = set()
        self.twitch_badge_cache: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, user_id: int, message: dict[str, Any]):
        # Keep the most recent 300 messages for Omni scrollback. The browser
        # viewport is independent; it can show the latest messages while older
        # retained messages remain available by scrolling upward.
        history = self.messages.setdefault(user_id, deque(maxlen=300))
        history.append(message)
        async with self._lock:
            stale = []
            for websocket in tuple(self.clients.get(user_id, set())):
                try:
                    await websocket.send_json({"type": "message", "message": message})
                except Exception:
                    stale.append(websocket)
            for websocket in stale:
                self.clients.get(user_id, set()).discard(websocket)

    async def set_status(self, user_id: int, platform: str, value: str):
        self.status.setdefault(user_id, {})[platform] = value
        async with self._lock:
            stale = []
            for websocket in tuple(self.clients.get(user_id, set())):
                try:
                    await websocket.send_json({"type": "status", "platform": platform, "status": value})
                except Exception:
                    stale.append(websocket)
            for websocket in stale:
                self.clients.get(user_id, set()).discard(websocket)

    async def attach(self, user_id: int, websocket, snapshot_limit: int = 300):
        await websocket.accept()
        self.clients.setdefault(user_id, set()).add(websocket)
        history = list(self.messages.get(user_id, []))
        await websocket.send_json({"type": "snapshot", "messages": history[-max(1, min(300, int(snapshot_limit))):], "status": self.status.get(user_id, {})})

    def detach(self, user_id: int, websocket):
        self.clients.get(user_id, set()).discard(websocket)

    async def mark_deleted(self, user_id: int, platform: str, message_id: str | None, deleted_by: str | None = None):
        if not message_id:
            return
        for item in self.messages.get(user_id, []):
            if item.get("platform") == platform and str(item.get("id")) == str(message_id):
                item["deleted"] = True
                item["deleted_by"] = deleted_by or "Moderator"
        async with self._lock:
            for websocket in tuple(self.clients.get(user_id, set())):
                try:
                    await websocket.send_json({"type": "message_deleted", "platform": platform, "message_id": str(message_id), "deleted_by": deleted_by or "Moderator"})
                except Exception:
                    self.clients.get(user_id, set()).discard(websocket)

    async def publish_system(self, user_id: int, message: dict[str, Any]):
        await self.publish(user_id, message)

    async def start_for_user(self, user_id: int):
        db = SessionLocal()
        try:
            connections = db.query(ChatConnection).filter(ChatConnection.user_id == user_id).all()
            configs = {
                row.platform: {
                    "access_token": decrypt_token(row.access_token),
                    "refresh_token": decrypt_token(row.refresh_token),
                    "expires_at": row.expires_at,
                    "platform_user_id": row.platform_user_id,
                    "platform_login": row.platform_login,
                    "platform_display_name": row.platform_display_name,
                }
                for row in connections
            }
        finally:
            db.close()

        for platform in ("twitch", "youtube"):
            key = (user_id, platform)
            task = self.tasks.get(key)
            if task and not task.done():
                continue
            config = configs.get(platform)
            if not config:
                await self.set_status(user_id, platform, "Not connected")
                continue
            if platform == "youtube":
                channel_id = str(config.get("platform_user_id") or "")
                if not channel_id:
                    await self.set_status(user_id, "youtube", "Connected · missing YouTube channel ID")
                    continue
                subscribers = self.youtube_channel_subscribers.setdefault(channel_id, set())
                subscribers.add(user_id)
                shared_task = self.youtube_channel_tasks.get(channel_id)
                if shared_task and not shared_task.done():
                    self.tasks[key] = shared_task
                    continue
                shared_task = asyncio.create_task(
                    self._youtube_worker(user_id, config, channel_id),
                    name=f"chat-youtube-channel-{channel_id}",
                )
                self.youtube_channel_tasks[channel_id] = shared_task
                self.tasks[key] = shared_task
            else:
                self.tasks[key] = asyncio.create_task(
                    self._twitch_worker(user_id, config), name=f"chat-twitch-{user_id}"
                )

    def _record_identity(self, user_id: int, platform: str, platform_user_id: str | None,
                         username: str | None, is_member: bool, subscription_key: str | None = None,
                         tenure_months: int | None = None, preserve_unknown_tier: bool = False):
        if not platform_user_id:
            return {"subscription_key": subscription_key, "tenure_months": tenure_months}
        db = SessionLocal()
        try:
            row = db.query(ChatIdentity).filter_by(
                user_id=user_id, platform=platform, platform_user_id=str(platform_user_id)
            ).first()
            if row is None:
                row = ChatIdentity(
                    user_id=user_id, platform=platform, platform_user_id=str(platform_user_id),
                    username=username, is_member=bool(is_member)
                )
                db.add(row)
            row.username = username or row.username
            row.is_member = bool(is_member)
            if subscription_key is not None:
                row.subscription_key = subscription_key
            elif not preserve_unknown_tier:
                row.subscription_key = None
            if tenure_months is not None:
                try:
                    row.tenure_months = max(1, min(1200, int(tenure_months)))
                except (TypeError, ValueError):
                    pass
            elif not is_member:
                row.tenure_months = None
            db.commit()
            return {
                "subscription_key": row.subscription_key,
                "tenure_months": row.tenure_months,
            }
        finally:
            db.close()

    async def _twitch_subscription_tier(self, user_id: int, config: dict, chatter_id: str | None):
        if not chatter_id:
            return None
        import os
        from datetime import timedelta
        db = SessionLocal()
        try:
            cached = db.query(ChatIdentity).filter_by(
                user_id=user_id, platform="twitch", platform_user_id=str(chatter_id)
            ).first()
            if cached and cached.tier_checked_at:
                if datetime.utcnow() - cached.tier_checked_at < timedelta(hours=6):
                    return cached.subscription_key
        finally:
            db.close()
        client_id = os.getenv("TWITCH_CLIENT_ID")
        token = config.get("access_token")
        broadcaster_id = config.get("platform_user_id")
        if not client_id or not token or not broadcaster_id:
            return None
        try:
            response = await asyncio.to_thread(
                requests.get,
                "https://api.twitch.tv/helix/subscriptions",
                headers={"Client-ID": client_id, "Authorization": f"Bearer {token}"},
                params={"broadcaster_id": broadcaster_id, "user_id": str(chatter_id)},
                timeout=12,
            )
            if response.status_code != 200:
                logger.debug("Twitch subscription lookup unavailable (%s)", response.status_code)
                return None
            rows = response.json().get("data", [])
            key = None
            if rows:
                key = {"1000": "twitch_t1", "2000": "twitch_t2", "3000": "twitch_t3"}.get(str(rows[0].get("tier")))
            # Cache only a successful API response; failures are retried on the next message.
            cache_db = SessionLocal()
            try:
                identity = cache_db.query(ChatIdentity).filter_by(
                    user_id=user_id, platform="twitch", platform_user_id=str(chatter_id)
                ).first()
                if identity is None:
                    identity = ChatIdentity(
                        user_id=user_id, platform="twitch", platform_user_id=str(chatter_id),
                        is_member=bool(key)
                    )
                    cache_db.add(identity)
                identity.subscription_key = key
                identity.is_member = bool(key)
                identity.tier_checked_at = datetime.utcnow()
                cache_db.commit()
            finally:
                cache_db.close()
            return key
        except Exception:
            logger.exception("Twitch subscription lookup failed for user %s", user_id)
            return None

    @staticmethod
    def _twitch_fragments(message):
        """Convert EventSub message fragments to safe, renderable text/emote segments."""
        segments = []
        bits = 0
        for fragment in message.get("fragments", []) or []:
            kind = fragment.get("type")
            value = fragment.get("text", "") or ""
            if kind == "emote":
                emote_id = (fragment.get("emote") or {}).get("id")
                if emote_id:
                    segments.append({
                        "type": "emote",
                        "text": value,
                        "url": f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/2.0",
                    })
                elif value:
                    segments.append({"type": "text", "text": value})
            elif kind == "cheermote":
                cheer = fragment.get("cheermote") or {}
                try:
                    bits += int(cheer.get("bits", 0))
                except (TypeError, ValueError):
                    pass
                if value:
                    segments.append({"type": "text", "text": value})
            elif value:
                segments.append({"type": "text", "text": value})
        return segments, bits

    async def _refresh_twitch_token_if_needed(self, user_id, token, refresh_token, expires_at, client_id, client_secret):
        from datetime import timedelta
        if not (expires_at and refresh_token and client_secret):
            return token, refresh_token, expires_at
        if datetime.utcnow() < (expires_at - timedelta(minutes=10)):
            return token, refresh_token, expires_at
        response = await asyncio.to_thread(
            requests.post, "https://id.twitch.tv/oauth2/token",
            data={"grant_type": "refresh_token", "refresh_token": refresh_token,
                  "client_id": client_id, "client_secret": client_secret},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        token = data["access_token"]
        refresh_token = data.get("refresh_token", refresh_token)
        expires_at = datetime.utcnow() + timedelta(seconds=int(data.get("expires_in", 14400)))
        await self._save_tokens(user_id, "twitch", token, refresh_token, expires_at)
        logger.info("Refreshed Twitch chat token before expiry for user %s", user_id)
        return token, refresh_token, expires_at

    async def _subscribe_twitch_eventsub(self, headers, session_id, broadcaster_id):
        subscriptions = [
            ("channel.chat.message", {"broadcaster_user_id": broadcaster_id, "user_id": broadcaster_id}),
            ("channel.chat.message_delete", {"broadcaster_user_id": broadcaster_id, "user_id": broadcaster_id}),
            ("channel.chat.notification", {"broadcaster_user_id": broadcaster_id, "user_id": broadcaster_id}),
            ("channel.cheer", {"broadcaster_user_id": broadcaster_id}),
        ]
        for event_type, condition in subscriptions:
            body = {
                "type": event_type, "version": "1", "condition": condition,
                "transport": {"method": "websocket", "session_id": session_id},
            }
            response = await asyncio.to_thread(
                requests.post, "https://api.twitch.tv/helix/eventsub/subscriptions",
                headers=headers, json=body, timeout=20
            )
            if response.status_code not in (200, 202, 409):
                logger.warning("Twitch EventSub %s subscription unavailable (%s): %s",
                               event_type, response.status_code, response.text[:250])

    @staticmethod
    def _tenure_badge(months):
        try:
            months = int(months)
        except (TypeError, ValueError):
            return None
        if months < 1:
            return None
        return f"{months // 12}Y" if months % 12 == 0 and months >= 12 else f"{months}M"

    async def _save_tokens(self, user_id: int, platform: str, access: str, refresh: str | None, expires_at):
        db = SessionLocal()
        try:
            row = db.query(ChatConnection).filter_by(user_id=user_id, platform=platform).first()
            if row:
                row.access_token = encrypt_token(access)
                if refresh:
                    row.refresh_token = encrypt_token(refresh)
                row.expires_at = expires_at
                db.commit()
        finally:
            db.close()

    async def _twitch_worker(self, user_id: int, config: dict):
        import os
        from datetime import timedelta

        token = config["access_token"]
        refresh_token = config.get("refresh_token")
        expires_at = config.get("expires_at")
        client_id = os.getenv("TWITCH_CLIENT_ID")
        client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not client_id:
            await self.set_status(user_id, "twitch", "Missing TWITCH_CLIENT_ID")
            return

        base_url = "wss://eventsub.wss.twitch.tv/ws"
        reconnecting = False
        retry_delay = 5
        await self.set_status(user_id, "twitch", "Connecting…")
        while True:
            try:
                token, refresh_token, expires_at = await self._refresh_twitch_token_if_needed(
                    user_id, token, refresh_token, expires_at, client_id, client_secret
                )

                async with websockets.connect(base_url, ping_interval=30, close_timeout=5, max_size=2**20) as ws:
                    first = json.loads(await ws.recv())
                    metadata = first.get("metadata", {})
                    if metadata.get("message_type") != "session_welcome":
                        raise RuntimeError("Twitch did not send an EventSub welcome message")
                    session_id = first["payload"]["session"]["id"]

                    # Twitch transfers active subscriptions to the reconnect URL.
                    # Only create a subscription after a brand-new session welcome.
                    if not reconnecting:
                        headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                        await self._subscribe_twitch_eventsub(
                            headers, session_id, str(config["platform_user_id"])
                        )
                    reconnecting = False
                    retry_delay = 5
                    await self.set_status(user_id, "twitch", "Connected")
                    badge_cache_key = str(config["platform_user_id"])
                    if badge_cache_key not in self.twitch_badge_cache:
                        try:
                            badge_headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
                            badge_map = {}
                            for badge_url, badge_params in (
                                ("https://api.twitch.tv/helix/chat/badges/global", {}),
                                ("https://api.twitch.tv/helix/chat/badges", {"broadcaster_id": badge_cache_key}),
                            ):
                                badge_response = await asyncio.to_thread(
                                    requests.get, badge_url, headers=badge_headers,
                                    params=badge_params, timeout=15
                                )
                                badge_response.raise_for_status()
                                for badge_set in badge_response.json().get("data", []):
                                    for version in badge_set.get("versions", []):
                                        badge_set_id = str(badge_set.get("set_id") or "badge")
                                        badge_map[f"{badge_set_id}:{version.get('id')}"] = {
                                            "url": version.get("image_url_2x") or version.get("image_url_1x"),
                                            # Keep the tooltip/alt text human-readable. The set name
                                            # is already represented by the badge itself; prefixing
                                            # it here produced labels such as "broadcaster Broadcaster".
                                            "title": str(version.get("title") or badge_set_id.replace("_", " ").title()),
                                            "set_id": badge_set_id,
                                        }
                            self.twitch_badge_cache[badge_cache_key] = badge_map
                        except Exception:
                            logger.info("Twitch badge artwork unavailable for user %s", user_id)
                            self.twitch_badge_cache[badge_cache_key] = {}

                    while True:
                        raw = await ws.recv()
                        token, refresh_token, expires_at = await self._refresh_twitch_token_if_needed(
                            user_id, token, refresh_token, expires_at, client_id, client_secret
                        )
                        packet = json.loads(raw)
                        kind = packet.get("metadata", {}).get("message_type")
                        if kind == "session_keepalive":
                            continue
                        if kind == "session_reconnect":
                            base_url = packet.get("payload", {}).get("session", {}).get("reconnect_url") or base_url
                            reconnecting = True
                            break
                        if kind == "revocation":
                            raise RuntimeError("Twitch revoked the chat subscription")
                        if kind != "notification":
                            continue
                        event = packet.get("payload", {}).get("event", {})
                        subscription_type = packet.get("metadata", {}).get("subscription_type")
                        if subscription_type == "channel.chat.message_delete":
                            await self.mark_deleted(user_id, "twitch", event.get("message_id"), event.get("moderator_user_name"))
                            continue
                        if subscription_type == "channel.chat.notification":
                            notice = event.get("notice_type", "community_event")
                            notice_map = {
                                "sub": ("NEW SUBSCRIPTION", "sub"),
                                "resub": ("RESUBSCRIPTION", "resub"),
                                "sub_gift": ("GIFTED SUBSCRIPTION", "sub_gift"),
                                "community_sub_gift": ("COMMUNITY GIFT SUBS", "community_sub_gift"),
                                "gift_paid_upgrade": ("GIFT SUB UPGRADE", "gift_upgrade"),
                                "prime_paid_upgrade": ("PRIME UPGRADE", "prime_upgrade"),
                                "raid": ("RAID", "raid"),
                                "bits_badge_tier": ("BITS BADGE MILESTONE", "bits"),
                                "announcement": ("ANNOUNCEMENT", "announcement"),
                                "charity_donation": ("CHARITY DONATION", "charity"),
                                "unraid": ("RAID ENDED", "unraid"),
                                "shared_chat_sub": ("SHARED CHAT SUBSCRIPTION", "shared_chat_sub"),
                                "shared_chat_resub": ("SHARED CHAT RESUBSCRIPTION", "shared_chat_resub"),
                                "shared_chat_sub_gift": ("SHARED CHAT GIFTED SUBSCRIPTION", "shared_chat_sub_gift"),
                                "shared_chat_community_sub_gift": ("SHARED CHAT COMMUNITY GIFTS", "shared_chat_community_sub_gift"),
                                "shared_chat_raid": ("SHARED CHAT RAID", "shared_chat_raid"),
                                "pay_it_forward": ("PAY IT FORWARD", "pay_it_forward"),
                                "community_pay_it_forward": ("COMMUNITY PAY IT FORWARD", "community_pay_it_forward"),
                                "standard_pay_forward": ("PAY IT FORWARD", "standard_pay_forward"),
                                "power_up": ("POWER UP", "power_up"),
                                "gigantified_emote": ("GIGANTIFIED EMOTE", "gigantified_emote"),
                                "message_effect": ("MESSAGE EFFECT", "message_effect"),
                            }
                            if notice in notice_map:
                                title, event_kind = notice_map[notice]
                            else:
                                readable_notice = str(notice or "unknown").replace("_", " ").strip().upper()
                                title, event_kind = (f"TWITCH: {readable_notice}", str(notice or "unknown"))
                            nested_key = {
                                "sub": "sub", "resub": "resub", "sub_gift": "sub_gift",
                                "community_sub_gift": "community_sub_gift", "raid": "raid",
                                "charity_donation": "charity_donation",
                            }.get(notice)
                            detail_source = event.get(nested_key, {}) if nested_key else {}
                            if not isinstance(detail_source, dict):
                                detail_source = {}
                            detail_source = {**event, **detail_source}
                            chatter_name = (event.get("chatter_user_name") or event.get("user_name")
                                            or event.get("broadcaster_user_name") or event.get("gifter_user_name")
                                            or event.get("user_login") or "Unknown user")
                            recipient = (detail_source.get("recipient_user_name") or detail_source.get("recipient_user_login")
                                         or detail_source.get("gifter_user_name"))
                            tier_value = str(detail_source.get("sub_tier") or detail_source.get("tier") or "")
                            tier_label = {"1000": "Tier 1", "2000": "Tier 2", "3000": "Tier 3"}.get(tier_value, f"Tier {tier_value}" if tier_value else "")
                            details = []
                            if notice == "sub_gift":
                                details.append(f"Gifted {tier_label + ' ' if tier_label else ''}subscription" + (f" to {recipient}" if recipient else ""))
                            elif notice == "community_sub_gift":
                                count = int(detail_source.get("total") or 0)
                                details.append(f"Gifted {count} subscriptions to the community" if count else "Gifted community subscriptions")
                                cumulative = detail_source.get("cumulative_total")
                                if cumulative:
                                    details.append(f"{cumulative} total community gifts")
                            elif notice in {"sub", "resub"}:
                                months = detail_source.get("cumulative_months") or detail_source.get("duration_months")
                                details.append("Subscribed" if notice == "sub" else "Resubscribed")
                                if months:
                                    details.append(f"{months} months")
                                if tier_label:
                                    details.append(tier_label)
                            elif notice == "raid":
                                viewers = detail_source.get("viewer_count")
                                details.append(f"Raided with {viewers} viewers" if viewers is not None else "Raided the channel")
                            elif notice == "charity_donation":
                                amount = detail_source.get("amount") or detail_source.get("amount_value")
                                currency = detail_source.get("currency") or detail_source.get("currency_code")
                                details.append(f"Donated {amount} {currency or ''}".strip() if amount else "Made a charity donation")
                            else:
                                detail_keys = (
                                    "cumulative_months", "streak_months", "duration_months", "total",
                                    "recipient_user_name", "recipient_user_login", "bits", "viewer_count",
                                    "amount", "currency", "amount_value", "currency_code", "message",
                                    "emote", "power_up_type", "shared_chat_session_id",
                                )
                                for key in detail_keys:
                                    value = detail_source.get(key)
                                    if value not in (None, "", 0) and not isinstance(value, (dict, list)):
                                        details.append(f"{key.replace('_', ' ').title()}: {value}")
                                if tier_label:
                                    details.append(tier_label)
                            detail_text = " · ".join(details) or title
                            await self.publish_system(user_id, {
                                "id": packet.get("metadata", {}).get("message_id") or f"twitch-event-{datetime.now(timezone.utc).timestamp()}",
                                "platform": "twitch", "username": chatter_name,
                                "user_id": (event.get("chatter_user_id") or event.get("user_id")
                                            or event.get("broadcaster_user_id") or event.get("gifter_user_id")),
                                "text": detail_text,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "event": True, "event_type": event_kind, "event_title": title,
                                "event_detail": detail_text,
                                "moderator": False, "badges": [], "badge_items": [],
                            })
                            continue
                        if subscription_type == "channel.cheer":
                            bits = int(event.get("bits", 0) or 0)
                            await self.publish_system(user_id, {
                                "id": packet.get("metadata", {}).get("message_id") or f"twitch-cheer-{datetime.now(timezone.utc).timestamp()}",
                                "platform": "twitch", "username": event.get("user_name") or "Anonymous",
                                "user_id": event.get("user_id"), "text": event.get("message") or f"Cheered {bits} Bits",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "event": True, "event_type": "cheer", "event_title": "CHEER",
                                "event_detail": f"{bits:,} Bits", "bits": bits,
                                "badges": [], "badge_items": [],
                            })
                            continue
                        message = event.get("message", {})
                        text = message.get("text", "")
                        segments, fragment_bits = self._twitch_fragments(message)
                        if not text:
                            continue
                        badge_rows = event.get("badges", [])
                        badge_sets = {badge.get("set_id") for badge in badge_rows if badge.get("set_id")}
                        subscriber_badge = next((badge for badge in badge_rows if badge.get("set_id") in {"subscriber", "founder"}), None)
                        chatter_id = event.get("chatter_user_id")
                        tenure_months = None
                        if subscriber_badge:
                            try:
                                tenure_months = int(subscriber_badge.get("info") or subscriber_badge.get("id"))
                            except (TypeError, ValueError):
                                tenure_months = None
                            tier_key = await self._twitch_subscription_tier(user_id, {
                                "access_token": token, "platform_user_id": config["platform_user_id"]
                            }, chatter_id)
                            identity = self._record_identity(
                                user_id, "twitch", chatter_id, event.get("chatter_user_name"),
                                True, tier_key, tenure_months, preserve_unknown_tier=True
                            )
                        else:
                            identity = self._record_identity(
                                user_id, "twitch", chatter_id, event.get("chatter_user_name"), False
                            )
                        tier_labels = {"twitch_t1": "T1", "twitch_t2": "T2", "twitch_t3": "T3"}
                        badge_items = []
                        badge_labels = []
                        badge_cache = self.twitch_badge_cache.get(str(config["platform_user_id"]), {})
                        for badge_row in badge_rows:
                            set_id = str(badge_row.get("set_id") or "badge")
                            badge_info = badge_cache.get(f"{set_id}:{badge_row.get('id')}", {})
                            clean_title = str(badge_info.get("title") or set_id.replace("_", " ").title())
                            # Keep one canonical badge record for rendering. If artwork is
                            # unavailable, the UI can show this clean title as a text fallback.
                            badge_items.append({
                                "url": badge_info.get("url"),
                                "title": clean_title,
                                "set_id": set_id,
                            })
                            if set_id != "subscriber":
                                badge_labels.append(set_id.replace("_", " ").title())

                        await self.publish(user_id, {
                            "id": message.get("message_id") or packet.get("metadata", {}).get("message_id"),
                            "platform": "twitch",
                            "username": event.get("chatter_user_name") or "Twitch user",
                            "user_id": chatter_id,
                            "text": text,
                            "timestamp": message.get("sent_at") or datetime.now(timezone.utc).isoformat(),
                            "color": event.get("color"),
                            "badges": badge_labels,
                            "badge_icons": [item["url"] for item in badge_items if item.get("url")],
                            "badge_items": badge_items,
                            "segments": segments,
                            "event": bool(fragment_bits),
                            "event_type": "cheer" if fragment_bits else None,
                            "event_title": "CHEER" if fragment_bits else None,
                            "event_detail": f"{fragment_bits:,} Bits" if fragment_bits else None,
                            "bits": fragment_bits or None,
                            "subscription_badge": tier_labels.get(identity.get("subscription_key")) or ("SUB" if subscriber_badge else None),
                            "tenure_badge": self._tenure_badge(identity.get("tenure_months")),
                            "moderator": bool({"moderator", "lead_moderator"} & badge_sets),
                            "lead_moderator": "lead_moderator" in badge_sets,
                            "broadcaster": "broadcaster" in badge_sets,
                            "vip": "vip" in badge_sets,
                        })

                if not reconnecting:
                    base_url = "wss://eventsub.wss.twitch.tv/ws"
                    await self.set_status(user_id, "twitch", "Reconnecting…")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Twitch chat connection retry for user %s", user_id)
                await self.set_status(user_id, "twitch", f"Reconnecting: {str(exc)[:150]}")
                base_url = "wss://eventsub.wss.twitch.tv/ws"
                reconnecting = False
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    async def _youtube_channel_status(self, channel_id: str, owner_user_id: int, value: str):
        subscribers = set(self.youtube_channel_subscribers.get(channel_id, {owner_user_id}))
        for subscriber_id in subscribers:
            await self.set_status(subscriber_id, "youtube", value)

    async def _youtube_channel_publish(self, channel_id: str, owner_user_id: int, message: dict[str, Any]):
        subscribers = set(self.youtube_channel_subscribers.get(channel_id, {owner_user_id}))
        for subscriber_id in subscribers:
            if message.get("user_id"):
                self._record_identity(
                    subscriber_id, "youtube", str(message.get("user_id")),
                    message.get("username"), bool(message.get("member")),
                    "youtube_member" if message.get("member") else None,
                )
            await self.publish(subscriber_id, dict(message))

    async def _youtube_channel_mark_deleted(self, channel_id: str, owner_user_id: int, message_id: str | None, deleted_by: str | None = None):
        subscribers = set(self.youtube_channel_subscribers.get(channel_id, {owner_user_id}))
        for subscriber_id in subscribers:
            await self.mark_deleted(subscriber_id, "youtube", message_id, deleted_by)

    def request_youtube_backup_connect(self, channel_id: str) -> None:
        """Queue one explicit YouTube API discovery attempt for this channel."""
        if channel_id:
            self.youtube_backup_connect_requests.add(str(channel_id))

    @staticmethod
    def _youtube_public_live(channel_id: str | None) -> tuple[bool | None, str | None]:
        """Check a channel's public /live page without consuming YouTube Data API quota."""
        if not channel_id:
            return False, None
        try:
            response = requests.get(
                f"https://www.youtube.com/channel/{channel_id}/live",
                headers={"User-Agent": "Mozilla/5.0 (compatible; LlamaQueue/1.0)"},
                timeout=12,
                allow_redirects=True,
            )
            if response.status_code == 404:
                return False, None
            if response.status_code != 200:
                return None, None
            html = response.text
            # /live may redirect to a watch URL. Only treat it as live when
            # YouTube's page explicitly marks the current broadcast as live now.
            live_now = bool(
                re.search(r'"isLiveNow"\s*:\s*true', html)
                or re.search(r'"isLive"\s*:\s*true', html)
            )
            if not live_now:
                return False, None
            video_id = None
            match = re.search(r'[?&]v=([A-Za-z0-9_-]{11})', response.url)
            if match:
                video_id = match.group(1)
            if not video_id:
                match = re.search(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', html)
                if match:
                    video_id = match.group(1)
            return True, video_id
        except requests.RequestException as exc:
            logger.warning("YouTube public live-page check failed for channel %s: %s", channel_id, exc)
            return None, None

    async def _youtube_worker(self, user_id: int, config: dict, channel_id: str | None = None):
        import os
        from datetime import timedelta

        channel_id = str(channel_id or config.get("platform_user_id") or "")
        try:
            credentials = Credentials(
                token=config["access_token"],
                refresh_token=config.get("refresh_token"),
                expiry=config.get("expires_at"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
            )
            youtube = await asyncio.to_thread(build, "youtube", "v3", credentials=credentials, cache_discovery=False)
            previous_chat_id = None
            previous_video_id = None
            page_token = None

            while True:
                if credentials.expired and credentials.refresh_token:
                    await asyncio.to_thread(credentials.refresh, GoogleRequest())
                    await self._save_tokens(user_id, "youtube", credentials.token, credentials.refresh_token, credentials.expiry)

                # Offline detection uses the public channel page, not the
                # quota-metered YouTube Data API. No API request is made while
                # the channel is offline.
                is_live, public_video_id = await asyncio.to_thread(
                    self._youtube_public_live, config.get("platform_user_id")
                )
                if is_live and public_video_id:
                    if previous_video_id and public_video_id != previous_video_id:
                        # A new live video means the old live-chat ID and resume
                        # cursor must not be reused for the new broadcast.
                        previous_chat_id = None
                        page_token = None
                        self.youtube_live_chat_ids.pop(user_id, None)
                        self._youtube_lookup_blocked_video.pop(user_id, None)
                    previous_video_id = public_video_id

                # The manual backup button is the only path that performs a
                # discovery lookup when public-page detection says the channel
                # is offline/unknown. It is one-shot per click, never a poll.
                if channel_id in self.youtube_backup_connect_requests:
                    self.youtube_backup_connect_requests.discard(channel_id)
                    if not is_live:
                        await self._youtube_channel_status(
                            channel_id, user_id, "Manual YouTube connection check…"
                        )
                        try:
                            backup_result = await asyncio.to_thread(
                                lambda: youtube.liveBroadcasts().list(
                                    part="id,snippet,status", mine=True,
                                    broadcastType="all", maxResults=50
                                ).execute()
                            )
                            for broadcast in backup_result.get("items", []):
                                if broadcast.get("status", {}).get("lifeCycleStatus") != "live":
                                    continue
                                backup_chat_id = broadcast.get("snippet", {}).get("liveChatId")
                                if backup_chat_id:
                                    live_chat_id = backup_chat_id
                                    previous_chat_id = backup_chat_id
                                    previous_video_id = broadcast.get("id") or public_video_id
                                    self.youtube_live_chat_ids[user_id] = backup_chat_id
                                    is_live = True
                                    public_video_id = previous_video_id
                                    self._youtube_lookup_blocked_video.pop(user_id, None)
                                    break
                            if not is_live:
                                await self._youtube_channel_status(
                                    channel_id, user_id,
                                    "No active YouTube live chat found · automatic detection remains on"
                                )
                        except Exception as backup_error:
                            quota_exhausted = (
                                "quotaExceeded" in str(backup_error)
                                or getattr(backup_error, "reason", None) == "quotaExceeded"
                            )
                            label = "YouTube API quota exhausted" if quota_exhausted else "Backup check failed"
                            await self._youtube_channel_status(
                                channel_id, user_id,
                                f"{label} · automatic detection remains on"
                            )
                            logger.warning(
                                "Manual YouTube backup lookup failed for channel %s: %s",
                                channel_id, backup_error
                            )

                if is_live is None:
                    # A page/network failure is not proof that the broadcast ended.
                    # Keep the known chat ID and resume token intact.
                    if previous_chat_id:
                        live_chat_id = previous_chat_id
                    else:
                        await self._youtube_channel_status(channel_id, user_id, "Connected · checking live status")
                        await asyncio.sleep(30)
                        continue
                elif not is_live:
                    self.youtube_live_chat_ids.pop(user_id, None)
                    self._youtube_lookup_blocked_video.pop(user_id, None)
                    previous_chat_id = None
                    previous_video_id = None
                    page_token = None
                    await self._youtube_channel_status(channel_id, user_id, "Connected · waiting for a live stream")
                    await asyncio.sleep(45)
                    continue

                # Keep the known chat ID across transient StreamList disconnects.
                live_chat_id = previous_chat_id or self.youtube_live_chat_ids.get(user_id)
                if not live_chat_id:
                    # One discovery lookup per live video. Do not repeatedly
                    # spend quota if the live chat is unavailable or quota is exhausted.
                    lookup_key = public_video_id or "__unknown_live_video__"
                    if lookup_key == self._youtube_lookup_blocked_video.get(user_id):
                        await self._youtube_channel_status(channel_id, user_id, "Live detected · chat lookup unavailable")
                        await asyncio.sleep(45)
                        continue
                    try:
                        result = await asyncio.to_thread(
                            lambda: youtube.liveBroadcasts().list(
                                part="id,snippet,status", mine=True,
                                broadcastType="all", maxResults=50
                            ).execute()
                        )
                        for broadcast in result.get("items", []):
                            if broadcast.get("status", {}).get("lifeCycleStatus") == "live":
                                live_chat_id = broadcast.get("snippet", {}).get("liveChatId")
                                if live_chat_id:
                                    break
                    except Exception as lookup_error:
                        reason = getattr(lookup_error, "reason", None)
                        quota_exhausted = "quotaExceeded" in str(lookup_error) or reason == "quotaExceeded"
                        self._youtube_lookup_blocked_video[user_id] = lookup_key
                        if quota_exhausted:
                            await self._youtube_channel_status(channel_id, user_id, "Live detected · YouTube API quota exhausted")
                            logger.error("YouTube chat lookup hit quota for user %s; keeping worker alive", user_id)
                        else:
                            await self._youtube_channel_status(channel_id, user_id, "Live detected · chat lookup temporarily unavailable")
                            logger.warning("YouTube chat lookup failed for user %s; will not repeatedly spend quota: %s", user_id, lookup_error)
                        await asyncio.sleep(60)
                        continue
                    if not live_chat_id:
                        self._youtube_lookup_blocked_video[user_id] = lookup_key
                        await self._youtube_channel_status(channel_id, user_id, "Live detected · no live chat available")
                        await asyncio.sleep(45)
                        continue

                self.youtube_live_chat_ids[user_id] = live_chat_id
                if live_chat_id != previous_chat_id:
                    page_token = None
                    previous_chat_id = live_chat_id
                    self._youtube_lookup_blocked_video.pop(user_id, None)

                await self._youtube_channel_status(channel_id, user_id, "Connected · receiving chat")
                channel = grpc.aio.secure_channel("youtube.googleapis.com:443", grpc.ssl_channel_credentials())
                rpc = channel.unary_stream(
                    "/youtube.api.v3.V3DataLiveChatMessageService/StreamList",
                    request_serializer=lambda request: request.SerializeToString(),
                    response_deserializer=LiveChatMessageListResponse.FromString,
                )
                try:
                    request = LiveChatMessageListRequest(
                        live_chat_id=live_chat_id,
                        part=["snippet", "authorDetails"],
                        profile_image_size=48,
                    )
                    if page_token:
                        request.page_token = page_token
                    call = rpc(request, metadata=(("authorization", f"Bearer {credentials.token}"),))
                    try:
                        async for response in call:
                            if response.next_page_token:
                                page_token = response.next_page_token
                            for item in response.items:
                                snippet = item.snippet
                                author = item.author_details
                                if getattr(snippet, "type", 0) == 2:  # TOMBSTONE: message was removed by a moderator
                                    await self._youtube_channel_mark_deleted(channel_id, user_id, item.id, "Moderator")
                                    continue
                                milestone_months = None
                                milestone_comment = ""
                                new_member = False
                                if snippet.HasField("member_milestone_chat_details"):
                                    milestone = snippet.member_milestone_chat_details
                                    milestone_months = int(milestone.member_month) if milestone.HasField("member_month") else None
                                    milestone_comment = milestone.user_comment or ""
                                if snippet.HasField("new_sponsor_details"):
                                    new_member = True
                                is_member = bool(getattr(author, "is_chat_sponsor", False) or milestone_months or new_member)
                                identity = self._record_identity(
                                    user_id, "youtube", author.channel_id or None,
                                    author.display_name or "YouTube user", is_member,
                                    "youtube_member" if is_member else None, milestone_months
                                )
                                text = ""
                                event_title = None
                                event_detail = ""
                                event_type = None
                                if snippet.HasField("text_message_details"):
                                    text = snippet.text_message_details.message_text
                                elif milestone_comment:
                                    text = milestone_comment
                                    event_title = "Membership milestone"
                                    event_type = "membership_milestone"
                                    event_detail = f"{milestone_months or ''} months"
                                elif snippet.HasField("display_message"):
                                    text = snippet.display_message
                                if snippet.HasField("super_chat_details"):
                                    details = snippet.super_chat_details
                                    amount = details.amount_display_string or (
                                        f"{details.currency} {int(details.amount_micros or 0) / 1000000:.2f}".strip()
                                    )
                                    event_title = "SUPER CHAT"
                                    event_type = "super_chat"
                                    event_detail = amount
                                    text = details.user_comment or text or f"Sent a Super Chat: {amount}"
                                if snippet.HasField("membership_gifting_details"):
                                    details = snippet.membership_gifting_details
                                    count = int(details.gift_memberships_count or 0)
                                    event_title = "Gifted memberships"
                                    event_type = "membership_gift"
                                    event_detail = f"{count} memberships · {details.gift_memberships_level_name}".strip(" ·")
                                    text = text or event_detail
                                if snippet.HasField("gift_membership_received_details"):
                                    details = snippet.gift_membership_received_details
                                    event_title = "Gift membership received"
                                    event_type = "membership_gift_received"
                                    event_detail = details.member_level_name or "YouTube membership"
                                    if details.gifter_channel_id:
                                        event_detail = f"Gift from channel {details.gifter_channel_id} · {event_detail}"
                                    text = text or f"Received a gifted membership · {event_detail}"
                                if new_member and not event_title:
                                    event_title = "New channel member"
                                    event_type = "new_member"
                                    text = text or "Joined as a channel member"
                                if not text and not event_title:
                                    continue
                                await self._youtube_channel_publish(channel_id, user_id, {
                                    "id": item.id,
                                    "platform": "youtube",
                                    "username": author.display_name or "YouTube user",
                                    "user_id": author.channel_id or None,
                                    "text": text,
                                    "timestamp": snippet.published_at or datetime.now(timezone.utc).isoformat(),
                                    "avatar": author.profile_image_url or None,
                                    "verified": author.is_verified,
                                    "moderator": author.is_chat_moderator,
                                    "owner": author.is_chat_owner,
                                    "member": is_member,
                                    "subscription_badge": "MEM" if is_member else None,
                                    "tenure_badge": self._tenure_badge(identity.get("tenure_months")),
                                    "badges": (["Moderator"] if author.is_chat_moderator else []) + (["Verified"] if author.is_verified else []) + (["Owner"] if author.is_chat_owner else []),
                                    "event": bool(event_title),
                                    "event_type": event_type,
                                    "event_title": event_title,
                                    "event_detail": event_detail,
                                })
                    except grpc.aio.AioRpcError as stream_error:
                        logger.info("YouTube live chat stream ended for user %s: %s", user_id, stream_error)
                        await self._youtube_channel_status(channel_id, user_id, "Reconnecting…")
                    except Exception as stream_error:
                        logger.warning("YouTube live chat stream error for user %s: %s", user_id, stream_error)
                        await self._youtube_channel_status(channel_id, user_id, "Connection interrupted · reconnecting…")
                finally:
                    await channel.close()

                # The stream normally ends when the broadcast ends or the network
                # drops. Re-discover the active chat and resume with pageToken.
                await self._youtube_channel_status(channel_id, user_id, "Reconnecting…")
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("YouTube chat worker stopped for user %s", user_id)
            await self._youtube_channel_status(channel_id, user_id, f"Connection error: {str(exc)[:180]}")


chat_hub = ChatHub()
