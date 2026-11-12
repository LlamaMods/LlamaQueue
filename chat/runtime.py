import asyncio
import json
import logging
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
        self._lock = asyncio.Lock()

    async def publish(self, user_id: int, message: dict[str, Any]):
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

    async def attach(self, user_id: int, websocket):
        await websocket.accept()
        self.clients.setdefault(user_id, set()).add(websocket)
        await websocket.send_json({"type": "snapshot", "messages": list(self.messages.get(user_id, [])), "status": self.status.get(user_id, {})})

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
            worker = self._twitch_worker if platform == "twitch" else self._youtube_worker
            self.tasks[key] = asyncio.create_task(worker(user_id, config), name=f"chat-{platform}-{user_id}")

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
                if expires_at and datetime.utcnow() >= (expires_at - timedelta(minutes=5)) and refresh_token and client_secret:
                    refreshed = await asyncio.to_thread(
                        requests.post,
                        "https://id.twitch.tv/oauth2/token",
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                            "client_id": client_id,
                            "client_secret": client_secret,
                        },
                        timeout=20,
                    )
                    refreshed.raise_for_status()
                    token_data = refreshed.json()
                    token = token_data["access_token"]
                    refresh_token = token_data.get("refresh_token", refresh_token)
                    expires_at = datetime.utcnow() + timedelta(seconds=int(token_data.get("expires_in", 14400)))
                    await self._save_tokens(user_id, "twitch", token, refresh_token, expires_at)

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
                        body = {
                            "type": "channel.chat.message",
                            "version": "1",
                            "condition": {"broadcaster_user_id": config["platform_user_id"], "user_id": config["platform_user_id"]},
                            "transport": {"method": "websocket", "session_id": session_id},
                        }
                        response = await asyncio.to_thread(requests.post, "https://api.twitch.tv/helix/eventsub/subscriptions", headers=headers, json=body, timeout=20)
                        if response.status_code not in (200, 202, 409):
                            raise RuntimeError(f"Twitch EventSub subscription failed ({response.status_code}): {response.text[:300]}")
                        # Message deletion events keep the dashboard in sync with moderator actions.
                        delete_body = {
                            "type": "channel.chat.message_delete", "version": "1",
                            "condition": {"broadcaster_user_id": config["platform_user_id"], "user_id": config["platform_user_id"]},
                            "transport": {"method": "websocket", "session_id": session_id},
                        }
                        delete_response = await asyncio.to_thread(requests.post, "https://api.twitch.tv/helix/eventsub/subscriptions", headers=headers, json=delete_body, timeout=20)
                        if delete_response.status_code not in (200, 202, 409):
                            logger.warning("Twitch deletion events unavailable for user %s: %s", user_id, delete_response.text[:250])
                    reconnecting = False
                    retry_delay = 5
                    await self.set_status(user_id, "twitch", "Connected")

                    while True:
                        raw = await ws.recv()
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
                        if packet.get("metadata", {}).get("subscription_type") == "channel.chat.message_delete":
                            await self.mark_deleted(user_id, "twitch", event.get("message_id"), event.get("moderator_user_name"))
                            continue
                        message = event.get("message", {})
                        text = message.get("text", "")
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
                        await self.publish(user_id, {
                            "id": message.get("message_id") or packet.get("metadata", {}).get("message_id"),
                            "platform": "twitch",
                            "username": event.get("chatter_user_name") or "Twitch user",
                            "user_id": chatter_id,
                            "text": text,
                            "timestamp": message.get("sent_at") or datetime.now(timezone.utc).isoformat(),
                            "color": event.get("color"),
                            "badges": [f"{badge.get('set_id')} {badge.get('id')}".strip() for badge in badge_rows if badge.get("set_id") != "subscriber"],
                            "subscription_badge": tier_labels.get(identity.get("subscription_key")) or ("SUB" if subscriber_badge else None),
                            "tenure_badge": self._tenure_badge(identity.get("tenure_months")),
                            "moderator": "moderator" in badge_sets,
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

    async def _youtube_worker(self, user_id: int, config: dict):
        import os
        from datetime import timedelta

        try:
            credentials = Credentials(
                token=config["access_token"],
                refresh_token=config.get("refresh_token"),
                expiry=config.get("expires_at"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=["https://www.googleapis.com/auth/youtube.readonly"],
            )
            youtube = await asyncio.to_thread(build, "youtube", "v3", credentials=credentials, cache_discovery=False)
            previous_chat_id = None
            page_token = None

            while True:
                if credentials.expired and credentials.refresh_token:
                    await asyncio.to_thread(credentials.refresh, GoogleRequest())
                    await self._save_tokens(user_id, "youtube", credentials.token, credentials.refresh_token, credentials.expiry)

                result = await asyncio.to_thread(
                    lambda: youtube.liveBroadcasts().list(part="id,snippet,status", mine=True, broadcastType="all", maxResults=50).execute()
                )
                live_chat_id = None
                for broadcast in result.get("items", []):
                    if broadcast.get("status", {}).get("lifeCycleStatus") == "live":
                        live_chat_id = broadcast.get("snippet", {}).get("liveChatId")
                        if live_chat_id:
                            break

                if not live_chat_id:
                    self.youtube_live_chat_ids.pop(user_id, None)
                    await self.set_status(user_id, "youtube", "Connected · waiting for a live stream")
                    await asyncio.sleep(45)
                    continue

                self.youtube_live_chat_ids[user_id] = live_chat_id
                if live_chat_id != previous_chat_id:
                    page_token = None
                    previous_chat_id = live_chat_id

                await self.set_status(user_id, "youtube", "Connected · receiving chat")
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
                                    await self.mark_deleted(user_id, "youtube", item.id, "Moderator")
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
                                if snippet.HasField("text_message_details"):
                                    text = snippet.text_message_details.message_text
                                elif milestone_comment:
                                    text = milestone_comment
                                elif snippet.HasField("display_message"):
                                    text = snippet.display_message
                                if not text:
                                    continue
                                await self.publish(user_id, {
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
                                })
                    except grpc.aio.AioRpcError as stream_error:
                        logger.info("YouTube live chat stream ended for user %s: %s", user_id, stream_error)
                        await self.set_status(user_id, "youtube", "Reconnecting…")
                finally:
                    await channel.close()

                # The stream normally ends when the broadcast ends or the network
                # drops. Re-discover the active chat and resume with pageToken.
                await self.set_status(user_id, "youtube", "Reconnecting…")
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("YouTube chat worker stopped for user %s", user_id)
            await self.set_status(user_id, "youtube", f"Connection error: {str(exc)[:180]}")


chat_hub = ChatHub()
