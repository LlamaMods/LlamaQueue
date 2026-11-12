from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import requests

from auth.google import oauth as google_oauth
from auth.twitch import oauth as twitch_oauth
from auth.nightbot import oauth as nightbot_oauth
from database.models import User, Community
from chat.models import ChatConnection
from chat.security import encrypt_token
from database.session import SessionLocal

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.get("/login/google")
async def login_google(request: Request):
    return await google_oauth.google.authorize_redirect(
        request,
        request.url_for("auth_callback"),
    )


@router.get("/login/twitch")
async def login_twitch(request: Request):
    return await twitch_oauth.twitch.authorize_redirect(
        request,
        request.url_for("twitch_callback"),
    )

@router.get("/login/nightbot")
async def login_nightbot(request: Request):
    redirect_uri = str(request.url_for("nightbot_callback"))

    return await nightbot_oauth.nightbot.authorize_redirect(
        request,
        redirect_uri,
    )    


def _save_chat_connection(db: Session, user_id: int, platform: str, token: dict,
                          platform_user_id: str, login: str | None,
                          display_name: str | None) -> bool:
    """Save chat credentials only for an explicit Unified Chat connection."""
    try:
        encrypted_access = encrypt_token(token.get("access_token"))
        encrypted_refresh = encrypt_token(token.get("refresh_token"))
    except RuntimeError:
        return False
    if not encrypted_access:
        return False
    expires_at = (
        datetime.utcfromtimestamp(float(token["expires_at"]))
        if token.get("expires_at") else None
    )
    row = db.query(ChatConnection).filter_by(user_id=user_id, platform=platform).first()
    if row is None:
        row = ChatConnection(user_id=user_id, platform=platform)
        db.add(row)
    row.access_token = encrypted_access
    if encrypted_refresh:
        row.refresh_token = encrypted_refresh
    row.expires_at = expires_at
    row.platform_user_id = str(platform_user_id)
    row.platform_login = login
    row.platform_display_name = display_name
    db.commit()
    return True


@router.get("/twitch/callback", name="twitch_callback")
async def twitch_callback(request: Request):
    token = await twitch_oauth.twitch.authorize_access_token(request)

    response = await twitch_oauth.twitch.get(
        "users",
        token=token,
        headers={
            "Client-ID": twitch_oauth.twitch.client_id,
        },
    )

    user = response.json()["data"][0]

    db: Session = SessionLocal()

    existing_user = (
        db.query(User)
        .filter(User.twitch_user_id == user["id"])
        .first()
    )

    if existing_user is None:
        existing_user = (
            db.query(User)
            .filter(User.email == user["email"])
            .first()
        )

    if existing_user is None:
        existing_user = User(
            email=user["email"],
            display_name=user["display_name"],
            avatar_url=user["profile_image_url"],
            twitch_user_id=user["id"],
            twitch_login=user["login"],
            twitch_display_name=user["display_name"],
            twitch_avatar=user["profile_image_url"],
        )
        db.add(existing_user)
    else:
        existing_user.email = user["email"]
        existing_user.display_name = user["display_name"]
        existing_user.avatar_url = user["profile_image_url"]

        existing_user.twitch_user_id = user["id"]
        existing_user.twitch_login = user["login"]
        existing_user.twitch_display_name = user["display_name"]
        existing_user.twitch_avatar = user["profile_image_url"]

    db.commit()
    db.refresh(existing_user)

    community = (
        db.query(Community)
        .filter(Community.owner_user_id == existing_user.id)
        .first()
    )

    if community is None:
        community = Community(
            owner_user_id=existing_user.id,
            name=(
                existing_user.youtube_channel_name
                or existing_user.display_name
                or "My Community"
            ),
        )

        db.add(community)
        db.commit()
        db.refresh(community)

    request.session["user_id"] = existing_user.id
    request.session["community_id"] = community.id

    chat_intent = request.session.pop("chat_connect_platform", None)
    chat_saved = True
    if chat_intent == "twitch":
        chat_saved = _save_chat_connection(
            db, existing_user.id, "twitch", token, user["id"],
            user.get("login"), user.get("display_name")
        )
    db.close()

    if chat_intent == "twitch":
        return RedirectResponse(
            url="/chat?connected=twitch" if chat_saved else "/chat?error=chat_encryption",
            status_code=303,
        )
    return RedirectResponse(url="/")

@router.get("/nightbot/callback", name="nightbot_callback")
async def nightbot_callback(request: Request):
    token = await nightbot_oauth.nightbot.authorize_access_token(request)

    response = await nightbot_oauth.nightbot.get(
        "https://api.nightbot.tv/1/channel",
        token=token,
    )

    channel = response.json()["channel"]

    db: Session = SessionLocal()

    existing_user = (
        db.query(User)
        .filter(User.nightbot_user_id == channel["_id"])
        .first()
    )

    if existing_user is None:
        existing_user = (
            db.query(User)
            .filter(User.youtube_channel_id == channel["providerId"])
            .first()
        )

    if existing_user is None:
        db.close()
        return RedirectResponse("/")

    existing_user.nightbot_user_id = channel["_id"]
    existing_user.nightbot_provider = channel["provider"]
    existing_user.nightbot_provider_id = channel["providerId"]
    existing_user.nightbot_bot_id = channel["botId"]
    existing_user.nightbot_channel_name = channel["name"]
    existing_user.nightbot_display_name = channel["displayName"]
    existing_user.nightbot_avatar = channel["avatar"]

    existing_user.nightbot_access_token = token.get("access_token")
    existing_user.nightbot_refresh_token = token.get("refresh_token")

    db.commit()

    request.session["user_id"] = existing_user.id

    community = (
        db.query(Community)
        .filter(Community.owner_user_id == existing_user.id)
        .first()
    )

    if community:
        request.session["community_id"] = community.id

    db.close()

    return RedirectResponse(url="/")

@router.get("/callback/google", name="auth_callback")
async def auth_callback(request: Request):
    token = await google_oauth.google.authorize_access_token(request)

    user = token["userinfo"]

    youtube_channel_id = None
    youtube_channel_name = None
    youtube_channel_handle = None
    youtube_thumbnail = None

    access_token = token.get("access_token")

    if access_token:
        response = requests.get(\
            "https://www.googleapis.com/youtube/v3/channels",
            params={
                "part": "snippet",
                "mine": "true",
            },
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )

        if response.ok:
            data = response.json()

            if data.get("items"):
                channel = data["items"][0]
                snippet = channel["snippet"]

                youtube_channel_id = channel["id"]
                youtube_channel_name = snippet.get("title")
                youtube_channel_handle = snippet.get("customUrl")
                youtube_thumbnail = (
                    snippet.get("thumbnails", {})
                    .get("high", {})
                    .get("url")
                )

    db: Session = SessionLocal()

    existing_user = (
        db.query(User)
        .filter(User.google_user_id == user["sub"])
        .first()
    )

    if existing_user is None:
        existing_user = (
            db.query(User)
            .filter(User.email == user["email"])
            .first()
        )

    if existing_user is None:
        existing_user = User(
            email=user["email"],
            display_name=user["name"],
            avatar_url=user.get("picture"),
            google_user_id=user["sub"],
        )
        db.add(existing_user)

    existing_user.email = user["email"]
    existing_user.display_name = user["name"]
    existing_user.avatar_url = user.get("picture")

    existing_user.google_user_id = user["sub"]

    existing_user.youtube_channel_id = youtube_channel_id
    existing_user.youtube_channel_name = youtube_channel_name
    existing_user.youtube_channel_handle = youtube_channel_handle
    existing_user.youtube_thumbnail = youtube_thumbnail

    db.commit()
    db.refresh(existing_user)

    community = (
        db.query(Community)
        .filter(Community.owner_user_id == existing_user.id)
        .first()
    )

    if community is None:
        community = Community(
            owner_user_id=existing_user.id,
            name=(
                existing_user.youtube_channel_name
                or existing_user.display_name
                or "My Community"
            ),
        )

        db.add(community)
        db.commit()
        db.refresh(community)

    request.session["user_id"] = existing_user.id
    request.session["community_id"] = community.id

    chat_intent = request.session.pop("chat_connect_platform", None)
    chat_saved = True
    if chat_intent == "youtube":
        chat_saved = _save_chat_connection(
            db, existing_user.id, "youtube", token,
            youtube_channel_id or existing_user.youtube_channel_id or user["sub"],
            youtube_channel_handle or existing_user.youtube_channel_handle,
            youtube_channel_name or existing_user.youtube_channel_name or "YouTube channel"
        )
    db.close()

    if chat_intent == "youtube":
        return RedirectResponse(
            url="/chat?connected=youtube" if chat_saved else "/chat?error=chat_encryption",
            status_code=303,
        )
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")