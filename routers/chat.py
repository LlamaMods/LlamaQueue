import os
import json
import secrets
import asyncio

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from chat.models import ChatConnection, ChatOverlayToken, ChatAppearance
from chat.runtime import chat_hub
from chat.security import decrypt_token
from auth.google import oauth as google_oauth
from auth.twitch import oauth as twitch_oauth
from database.models import CreatorSettings, UserAppearance
from database.session import SessionLocal

router = APIRouter(tags=["Unified Chat"])
templates = Jinja2Templates(directory="templates")

def _user(request: Request):
    return get_current_user(request)


DEFAULT_APPEARANCE = {
    "theme": "transparent", "fontSize": 16, "fontFamily": "Arial, sans-serif",
    "backgroundColor": "#111820", "backgroundOpacity": 78,
    "textColor": "#f3f5f7", "usernameColor": "#ffffff",
    "twitchColor": "#9146ff", "youtubeColor": "#e62117",
    "showPlatform": True, "showTimestamp": True, "showUsername": True,
    "showBadges": True, "maxMessages": 30, "messageSpacing": 7,
    "messageRadius": 8,
}


def _appearance(db: Session, user_id: int) -> dict:
    row = db.query(ChatAppearance).filter_by(user_id=user_id).first()
    try:
        saved = json.loads(row.settings_json) if row else {}
    except (TypeError, ValueError):
        saved = {}
    result = DEFAULT_APPEARANCE.copy()
    result.update({k: v for k, v in saved.items() if k in DEFAULT_APPEARANCE})
    # Restore yesterday's adjustable display limit. Alpha forced this to 60;
    # convert that Alpha-only forced value back to the prior 30-message default.
    try:
        message_limit = int(result.get("maxMessages", 30))
        if message_limit == 60:
            message_limit = 30
        result["maxMessages"] = max(5, min(100, message_limit))
    except (TypeError, ValueError):
        result["maxMessages"] = 30
    return result


def _overlay_token(db: Session, user_id: int) -> str:
    row = db.query(ChatOverlayToken).filter_by(user_id=user_id).first()
    if row:
        return row.token
    token = secrets.token_urlsafe(32)
    db.add(ChatOverlayToken(user_id=user_id, token=token))
    db.commit()
    return token



WEBSITE_APPEARANCE_DEFAULTS = {
    "background_color": "#101418",
    "surface_color": "#1B2128",
    "raised_surface_color": "#252D36",
    "accent_color": "#33C759",
    "accent_text_color": "#7BE495",
    "text_color": "#F4F7F8",
    "muted_text_color": "#A9B4BE",
    "border_color": "#2E3742",
    "font_family": "Segoe UI",
    "font_size": 16,
    "corner_radius": 14,
    "density": "comfortable",
}


def _website_appearance(db: Session, user_id: int) -> dict:
    row = db.query(UserAppearance).filter_by(user_id=user_id).first()
    result = WEBSITE_APPEARANCE_DEFAULTS.copy()
    if row is not None:
        for key in result:
            result[key] = getattr(row, key)
    return result


@router.get("/chat", response_class=HTMLResponse, name="chat_page")
async def chat_page(request: Request):
    user = _user(request)
    if user is None:
        return RedirectResponse("/", status_code=303)
    db = SessionLocal()
    try:
        connections = {row.platform: row for row in db.query(ChatConnection).filter_by(user_id=user.id).all()}
        creator_settings = db.query(CreatorSettings).filter_by(user_id=user.id).first()
        token = _overlay_token(db, user.id)
        overlay_url = str(request.url_for("chat_overlay", token=token))
        chat_appearance = _appearance(db, user.id)
        website_appearance = _website_appearance(db, user.id)
    finally:
        db.close()
    await chat_hub.start_for_user(user.id)
    return templates.TemplateResponse(request=request, name="chat.html", context={
        "request": request,
        "current_user": user,
        "settings": {
            "queue_name": creator_settings.queue_name if creator_settings else "LlamaQueue",
            "creator_name": creator_settings.creator_name if creator_settings else "LlamaQueue",
        },
        "title": "Unified Chat · LlamaQueue",
        "connections": connections,
        "overlay_url": overlay_url,
        "appearance": website_appearance,
        "chat_appearance": chat_appearance,
        "local_test_mode": (
            os.getenv("LLAMAQUEUE_LOCAL_TEST_MODE", "").lower() in {"1", "true", "yes"}
            and (request.url.hostname or "").lower().strip("[]") in {"localhost", "127.0.0.1", "::1"}
            and request.client is not None
            and request.client.host in {"127.0.0.1", "::1"}
        ),
    })


@router.get("/chat/connect/google")
async def connect_google_chat(request: Request):
    user = _user(request)
    if user is None:
        return RedirectResponse("/", status_code=303)
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        return RedirectResponse("/chat?error=google_config", status_code=303)
    # Reuse the already-registered Google callback. No new redirect URI is needed.
    request.session["chat_connect_platform"] = "youtube"
    return await google_oauth.google.authorize_redirect(
        request, request.url_for("auth_callback"), prompt="consent", access_type="offline",
        scope="openid email profile https://www.googleapis.com/auth/youtube.force-ssl"
    )


@router.get("/chat/connect/twitch")
async def connect_twitch_chat(request: Request):
    user = _user(request)
    if user is None:
        return RedirectResponse("/", status_code=303)
    if not os.getenv("TWITCH_CLIENT_ID") or not os.getenv("TWITCH_CLIENT_SECRET"):
        return RedirectResponse("/chat?error=twitch_config", status_code=303)
    # Reuse the existing Twitch callback and request chat-read permission only
    # for this explicit chat connection flow.
    request.session["chat_connect_platform"] = "twitch"
    return await twitch_oauth.twitch.authorize_redirect(
        request, request.url_for("twitch_callback"),
        scope="user:read:email user:read:chat user:write:chat moderator:manage:chat_messages moderator:manage:banned_users channel:read:subscriptions bits:read"
    )


@router.post("/chat/disconnect/{platform}")
async def disconnect_chat(request: Request, platform: str):
    user = _user(request)
    if user is None:
        return RedirectResponse("/", status_code=303)
    if platform not in ("twitch", "youtube"):
        return JSONResponse({"error": "Unknown platform"}, status_code=400)
    db = SessionLocal()
    try:
        row = db.query(ChatConnection).filter_by(user_id=user.id, platform=platform).first()
        if row:
            db.delete(row)
            db.commit()
    finally:
        db.close()
    task = chat_hub.tasks.get((user.id, platform))
    if task and not task.done():
        task.cancel()
    await chat_hub.set_status(user.id, platform, "Not connected")
    return RedirectResponse("/chat", status_code=303)


@router.get("/chat/api/appearance")
async def get_chat_appearance(request: Request):
    user = _user(request)
    if user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    db = SessionLocal()
    try:
        return JSONResponse(_appearance(db, user.id))
    finally:
        db.close()


@router.post("/chat/api/appearance")
async def save_chat_appearance(request: Request):
    user = _user(request)
    if user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Expected a settings object"}, status_code=400)

    # Strict allow-list and bounded values: never accept arbitrary CSS or HTML.
    clean = DEFAULT_APPEARANCE.copy()
    for key in ("showPlatform", "showTimestamp", "showUsername", "showBadges"):
        if key in payload:
            clean[key] = bool(payload[key])
    if payload.get("theme") in {"transparent", "dark", "light"}:
        clean["theme"] = payload["theme"]
    if payload.get("fontFamily") in {"Arial, sans-serif", "Verdana, sans-serif", "Tahoma, sans-serif", "Georgia, serif", "monospace"}:
        clean["fontFamily"] = payload["fontFamily"]
    for key, low, high in (("fontSize", 11, 28), ("backgroundOpacity", 0, 100), ("maxMessages", 5, 100), ("messageSpacing", 0, 20), ("messageRadius", 0, 24)):
        try:
            clean[key] = max(low, min(high, int(payload.get(key, clean[key]))))
        except (TypeError, ValueError):
            pass
    import re
    for key in ("backgroundColor", "textColor", "usernameColor", "twitchColor", "youtubeColor"):
        value = payload.get(key)
        if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            clean[key] = value

    db = SessionLocal()
    try:
        row = db.query(ChatAppearance).filter_by(user_id=user.id).first()
        if row is None:
            row = ChatAppearance(user_id=user.id, settings_json=json.dumps(clean))
            db.add(row)
        else:
            row.settings_json = json.dumps(clean)
        db.commit()
        return JSONResponse(clean)
    finally:
        db.close()


@router.post("/chat/api/send")
async def send_chat_message(request: Request):
    user = _user(request)
    if user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    message = str(payload.get("message", "")).strip()[:500]
    target = payload.get("target")
    if not message:
        return JSONResponse({"error": "Enter a message first."}, status_code=400)
    if target not in {"all", "twitch", "youtube"}:
        return JSONResponse({"error": "Choose a valid destination."}, status_code=400)

    import os
    import requests
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    db = SessionLocal()
    try:
        rows = {row.platform: row for row in db.query(ChatConnection).filter_by(user_id=user.id).all()}
        results = {}
        platforms = ("twitch", "youtube") if target == "all" else (target,)
        for platform in platforms:
            row = rows.get(platform)
            if not row:
                results[platform] = {"ok": False, "error": "Not connected"}
                continue
            token = decrypt_token(row.access_token)
            try:
                if platform == "twitch":
                    # The sender is the account whose OAuth token is stored on this
                    # connection. The broadcaster is the creator's channel, which
                    # may be a different account when a moderator connects.
                    broadcaster_id = str(user.twitch_user_id or row.platform_user_id)
                    sender_id = str(row.platform_user_id)
                    client_id = os.getenv("TWITCH_CLIENT_ID", "")
                    if not client_id or not broadcaster_id or not sender_id:
                        raise RuntimeError("Twitch connection is missing its channel or sender identity. Reconnect Twitch in Unified Chat.")
                    response = await asyncio.to_thread(
                        requests.post, "https://api.twitch.tv/helix/chat/messages",
                        headers={"Client-ID": client_id, "Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json={"broadcaster_id": broadcaster_id, "sender_id": sender_id, "message": message}, timeout=20)
                    if response.status_code not in (200, 201):
                        detail = ""
                        try:
                            detail = response.json().get("message", "")
                        except Exception:
                            detail = response.text[:160]
                        raise RuntimeError(f"Twitch rejected the message ({response.status_code}): {detail or 'Check the connected account and user:write:chat permission.'}")
                    try:
                        twitch_result = response.json().get("data", [{}])[0]
                    except Exception:
                        twitch_result = {}
                    if twitch_result.get("is_sent") is False:
                        drop = twitch_result.get("drop_reason") or {}
                        reason = drop.get("message") or drop.get("code") or "Twitch did not deliver the message."
                        raise RuntimeError(str(reason))
                    results[platform] = {"ok": True}
                else:
                    live_chat_id = chat_hub.youtube_live_chat_ids.get(user.id)
                    credentials = Credentials(token=token, refresh_token=decrypt_token(row.refresh_token),
                        token_uri="https://oauth2.googleapis.com/token", client_id=os.getenv("GOOGLE_CLIENT_ID"),
                        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"), expiry=row.expires_at,
                        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])
                    service = await asyncio.to_thread(build, "youtube", "v3", credentials=credentials, cache_discovery=False)
                    # If the listener has not populated its cache yet, ask YouTube
                    # for the active broadcast belonging to this connected channel.
                    if not live_chat_id:
                        broadcasts = await asyncio.to_thread(lambda: service.liveBroadcasts().list(
                            part="snippet,status", broadcastStatus="active", mine=True, maxResults=5
                        ).execute())
                        active = broadcasts.get("items", [])
                        live_chat_id = next((item.get("snippet", {}).get("liveChatId") for item in active
                                             if item.get("snippet", {}).get("liveChatId")), None)
                    if not live_chat_id:
                        raise RuntimeError("No active YouTube live chat was found for the connected channel.")
                    body = {"snippet": {"liveChatId": live_chat_id, "type": "textMessageEvent", "textMessageDetails": {"messageText": message}}}
                    await asyncio.to_thread(lambda: service.liveChatMessages().insert(part="snippet", body=body).execute())
                    results[platform] = {"ok": True}
            except Exception as exc:
                results[platform] = {"ok": False, "error": str(exc)[:220]}
        success = any(item.get("ok") for item in results.values())
        return JSONResponse({"results": results, "ok": success}, status_code=200 if success else 400)
    finally:
        db.close()


@router.post("/chat/api/moderate/delete")
async def delete_chat_message(request: Request):
    user = _user(request)
    if user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    platform = payload.get("platform")
    message_id = str(payload.get("message_id", ""))[:255]
    if platform not in {"twitch", "youtube"} or not message_id:
        return JSONResponse({"error": "A platform and message ID are required."}, status_code=400)

    import os
    import requests
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    db = SessionLocal()
    try:
        row = db.query(ChatConnection).filter_by(user_id=user.id, platform=platform).first()
        if not row:
            return JSONResponse({"error": "That platform is not connected."}, status_code=400)
        token = decrypt_token(row.access_token)
        if platform == "twitch":
            response = await asyncio.to_thread(
                requests.delete, "https://api.twitch.tv/helix/moderation/chat",
                headers={"Client-ID": os.getenv("TWITCH_CLIENT_ID", ""), "Authorization": f"Bearer {token}"},
                params={"broadcaster_id": str(user.twitch_user_id or row.platform_user_id), "moderator_id": str(row.platform_user_id), "message_id": message_id}, timeout=20)
            if response.status_code not in (200, 204):
                return JSONResponse({"error": f"Twitch rejected the delete ({response.status_code}): {response.text[:180]}. The connected chat account must be a moderator and have moderator:manage:chat_messages permission."}, status_code=403)
        else:
            credentials = Credentials(token=token, refresh_token=decrypt_token(row.refresh_token),
                token_uri="https://oauth2.googleapis.com/token", client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"), expiry=row.expires_at,
                scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])
            service = await asyncio.to_thread(build, "youtube", "v3", credentials=credentials, cache_discovery=False)
            await asyncio.to_thread(lambda: service.liveChatMessages().delete(id=message_id).execute())
        await chat_hub.mark_deleted(user.id, platform, message_id, "You")
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:240]}, status_code=403)
    finally:
        db.close()



@router.post("/chat/api/moderate/user")
async def moderate_chat_user(request: Request):
    user = _user(request)
    if user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    platform = payload.get("platform")
    platform_user_id = str(payload.get("user_id") or "")[:255]
    action = payload.get("action")
    if platform not in {"twitch", "youtube"} or not platform_user_id or action not in {"timeout", "ban"}:
        return JSONResponse({"error": "A platform, user ID, and valid moderation action are required."}, status_code=400)

    import os
    import requests
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    db = SessionLocal()
    try:
        row = db.query(ChatConnection).filter_by(user_id=user.id, platform=platform).first()
        if not row:
            return JSONResponse({"error": "That platform is not connected."}, status_code=400)
        token = decrypt_token(row.access_token)
        reason = "Moderated from LlamaQueue Omni"
        if platform == "twitch":
            body = {"data": {"user_id": platform_user_id, "reason": reason}}
            if action == "timeout":
                body["data"]["duration"] = 600
            response = await asyncio.to_thread(
                requests.post, "https://api.twitch.tv/helix/moderation/bans",
                headers={"Client-ID": os.getenv("TWITCH_CLIENT_ID", ""), "Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                params={"broadcaster_id": row.platform_user_id, "moderator_id": row.platform_user_id},
                json=body, timeout=20)
            if response.status_code not in (200, 201):
                return JSONResponse({"error": f"Twitch rejected the {action} ({response.status_code}). Check moderator permissions and reconnect."}, status_code=403)
        else:
            live_chat_id = chat_hub.youtube_live_chat_ids.get(user.id)
            if not live_chat_id:
                return JSONResponse({"error": "No active YouTube live chat was found."}, status_code=400)
            credentials = Credentials(token=token, refresh_token=decrypt_token(row.refresh_token),
                token_uri="https://oauth2.googleapis.com/token", client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"), expiry=row.expires_at,
                scopes=["https://www.googleapis.com/auth/youtube.force-ssl"])
            service = await asyncio.to_thread(build, "youtube", "v3", credentials=credentials, cache_discovery=False)
            snippet = {"liveChatId": live_chat_id, "type": "temporary" if action == "timeout" else "permanent",
                       "bannedUserDetails": {"channelId": platform_user_id}}
            if action == "timeout":
                snippet["banDurationSeconds"] = 600
            await asyncio.to_thread(lambda: service.liveChatBans().insert(part="snippet", body={"snippet": snippet}).execute())
        return JSONResponse({"ok": True, "action": action, "platform": platform})
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:240]}, status_code=403)
    finally:
        db.close()


@router.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket):
    user_id = websocket.session.get("user_id")
    if not user_id:
        await websocket.close(code=4401)
        return
    await chat_hub.attach(int(user_id), websocket)
    try:
        while True:
            incoming = await websocket.receive_text()
            if incoming == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        chat_hub.detach(int(user_id), websocket)


@router.get("/chat/overlay/{token}", response_class=HTMLResponse, name="chat_overlay")
async def chat_overlay(request: Request, token: str):
    db = SessionLocal()
    try:
        row = db.query(ChatOverlayToken).filter_by(token=token).first()
        if row is None:
            return HTMLResponse("Invalid LlamaQueue chat overlay URL.", status_code=404)
        user_id = row.user_id
        appearance = _appearance(db, user_id)
    finally:
        db.close()
    await chat_hub.start_for_user(user_id)
    return templates.TemplateResponse(request=request, name="chat_overlay.html", context={
        "request": request,
        "overlay_token": token,
        "appearance": appearance,
        "title": "LlamaQueue Chat Overlay",
    })


@router.websocket("/chat/overlay/ws/{token}")
async def chat_overlay_websocket(websocket: WebSocket, token: str):
    db = SessionLocal()
    try:
        row = db.query(ChatOverlayToken).filter_by(token=token).first()
        user_id = row.user_id if row else None
    finally:
        db.close()
    if user_id is None:
        await websocket.close(code=4404)
        return
    await chat_hub.attach(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        chat_hub.detach(user_id, websocket)
