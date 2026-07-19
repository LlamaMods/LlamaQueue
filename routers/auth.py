from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import requests

from auth.google import oauth as google_oauth
from auth.twitch import oauth as twitch_oauth
from database.models import User
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

    request.session["user_id"] = existing_user.id

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
        response = requests.get(
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

    request.session["user_id"] = existing_user.id

    db.close()

    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")