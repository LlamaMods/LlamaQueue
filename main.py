import os
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from auth.dependencies import get_current_user
from auth.google import oauth
from database.models import User, UserAppearance, QueueEntry, CreatorSettings
from database.models import CommandMapping
from database.session import Base, engine, SessionLocal
from database.session import SessionLocal
from services.user_resolver import get_creator_from_nightbot
from services.priority_service import PriorityService
from chat.models import QueueEntryPriority, QueuePrioritySettings, AppearancePreset, ChatConnection
from urllib.parse import parse_qs

from services.history_service import HistoryService
from services.moderator_service import ModeratorService
from routers.auth import router as auth_router
from routers.chat import router as chat_router
from chat.runtime import chat_hub

from services.command_service import CommandService
from services.nightbot_service import NightbotService
from services.queue_service import QueueService
from services.registration_service import RegistrationService
from services.settings_service import SettingsService
from typing import List
from bot import LlamaBot
from legal_policy import (PRIVACY_POLICY_VERSION, TERMS_VERSION, user_has_current_acceptance, save_acceptance)
from chat.security import decrypt_token, encrypt_token
from services.oauth_revocation import revoke_oauth_token

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Chat reception belongs to the server process, not to dashboard/OBS clients.
    await chat_hub.start_all_connected_users()
    try:
        yield
    finally:
        await chat_hub.shutdown()


app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def require_current_legal_acceptance(request: Request, call_next):
    path = request.url.path
    public_paths = ("/legal/", "/privacy", "/terms", "/data-deletion", "/static/")
    oauth_callbacks = ("/auth/callback/google", "/auth/twitch/callback", "/auth/nightbot/callback")
    if path.startswith(public_paths) or path in oauth_callbacks or path == "/auth/logout":
        return await call_next(request)
    user_id = request.session.get("user_id")
    if user_id:
        db = SessionLocal()
        try:
            accepted = user_has_current_acceptance(db, int(user_id))
        finally:
            db.close()
        if not accepted:
            return RedirectResponse("/legal/consent", status_code=303)
    return await call_next(request)


# Install SessionMiddleware after the custom middleware so signed session data
# is available to the legal-acceptance gate.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET"),
)


app.include_router(auth_router)
app.include_router(chat_router)

Base.metadata.create_all(bind=engine)


def _encrypt_legacy_nightbot_tokens():
    """Encrypt pre-existing Nightbot credentials once, preserving old values if already encrypted."""
    db = SessionLocal()
    try:
        users = db.query(User).filter(
            (User.nightbot_access_token.isnot(None)) | (User.nightbot_refresh_token.isnot(None))
        ).all()
        changed = False
        for user in users:
            for field in ("nightbot_access_token", "nightbot_refresh_token"):
                value = getattr(user, field)
                if not value:
                    continue
                try:
                    decrypt_token(value)
                except Exception:
                    encrypted = encrypt_token(value)
                    if encrypted:
                        setattr(user, field, encrypted)
                        changed = True
        if changed:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not migrate legacy Nightbot credentials to encrypted storage")
    finally:
        db.close()


_encrypt_legacy_nightbot_tokens()


app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

def get_services(request: Request):
    db = SessionLocal()

    current_user = get_current_user(request)

    if current_user is None:
        return None, None, None, None, None, db

    user = (
        db.query(User)
        .filter(User.id == current_user.id)
        .first()
    )

    queue = QueueService(db, user)
    registrations = RegistrationService(db, user)
    settings = SettingsService(db, user)
    history = HistoryService(db, user)
    moderators = ModeratorService(db, user)

    return queue, registrations, settings, history, moderators, db

def template_context(request: Request):
    current_user = get_current_user(request)
    appearance = {
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
    if current_user is not None:
        theme_db = SessionLocal()
        try:
            saved = theme_db.query(UserAppearance).filter_by(user_id=current_user.id).first()
            if saved is not None:
                for key in appearance:
                    appearance[key] = getattr(saved, key)
        finally:
            theme_db.close()
    return {"current_user": current_user, "appearance": appearance}


templates = Jinja2Templates(
    directory="templates",
    context_processors=[template_context],
)


def _legal_template(request: Request, name: str, **context):
    return templates.TemplateResponse(
        request=request, name=name, context={"request": request, **context}
    )


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy(request: Request):
    return _legal_template(request, "legal/privacy.html", title="Privacy Policy · LlamaQueue")


@app.get("/terms", response_class=HTMLResponse)
def terms_of_service(request: Request):
    return _legal_template(request, "legal/terms.html", title="Terms of Service · LlamaQueue")


@app.get("/legal/consent", response_class=HTMLResponse)
def legal_consent(request: Request, next: str = "/"):
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    return _legal_template(
        request, "legal/consent.html", title="Review LlamaQueue Policies",
        next_url=safe_next, error=None,
    )


@app.post("/legal/accept")
def accept_legal_terms(
    request: Request,
    accepted: str = Form(default=""),
    next_url: str = Form(default="/"),
):
    if accepted != "yes":
        safe_next = next_url if next_url.startswith("/") and not next_url.startswith("//") else "/"
        return _legal_template(
            request, "legal/consent.html", title="Review LlamaQueue Policies",
            next_url=safe_next, error="Please confirm that you have read and agree to both policies.",
        )
    request.session["legal_privacy_version"] = PRIVACY_POLICY_VERSION
    request.session["legal_terms_version"] = TERMS_VERSION
    request.session["legal_accepted_at"] = datetime.utcnow().isoformat()
    user_id = request.session.get("user_id")
    if user_id:
        db = SessionLocal()
        try:
            save_acceptance(db, int(user_id), request)
            db.commit()
        finally:
            db.close()
    safe_next = next_url if next_url.startswith("/") and not next_url.startswith("//") else "/"
    return RedirectResponse(safe_next, status_code=303)


@app.get("/data-deletion", response_class=HTMLResponse)
def data_deletion_page(request: Request):
    user = get_current_user(request)
    if user and not request.session.get("delete_account_nonce"):
        request.session["delete_account_nonce"] = secrets.token_urlsafe(32)
    return _legal_template(
        request, "legal/data_deletion.html", title="Data Deletion · LlamaQueue",
        current_user=user, csrf_token=request.session.get("delete_account_nonce"), error=None,
    )


@app.post("/data-deletion", response_class=HTMLResponse)
async def delete_account(
    request: Request,
    confirmation: str = Form(default=""),
    csrf_token: str = Form(default=""),
):
    user = get_current_user(request)
    expected = request.session.get("delete_account_nonce")
    if user is None:
        return RedirectResponse("/", status_code=303)
    if not expected or not secrets.compare_digest(expected, csrf_token):
        return _legal_template(request, "legal/data_deletion.html", title="Data Deletion · LlamaQueue",
                               current_user=user, csrf_token=expected, error="The form expired. Reload this page and try again.")
    if confirmation.strip() != "DELETE MY ACCOUNT":
        return _legal_template(request, "legal/data_deletion.html", title="Data Deletion · LlamaQueue",
                               current_user=user, csrf_token=expected, error="Type DELETE MY ACCOUNT exactly to confirm.")

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user.id).first()
        if db_user is None:
            request.session.clear()
            return RedirectResponse("/", status_code=303)
        connections = db.query(ChatConnection).filter_by(user_id=db_user.id).all()
        tokens_to_revoke = []
        for connection in connections:
            try:
                revoke_value = (
                    decrypt_token(connection.refresh_token) or decrypt_token(connection.access_token)
                    if connection.platform == "youtube" and connection.refresh_token
                    else decrypt_token(connection.access_token)
                )
                tokens_to_revoke.append((connection.platform, revoke_value))
            except Exception:
                logger.warning("Could not decrypt %s token during account deletion", connection.platform)
            await chat_hub.stop_for_user_platform(db_user.id, connection.platform)
        for platform, token in tokens_to_revoke:
            revoke_oauth_token(platform, token)
        await chat_hub.forget_user(db_user.id)

        # Delete all direct user-owned rows in FK-safe reverse dependency order.
        # Lobby history is left to the ORM relationship cascade so its player rows are removed too.
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in {"users", "lobby_history"} or "user_id" not in table.c:
                continue
            db.execute(table.delete().where(table.c.user_id == db_user.id))
        db.delete(db_user)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Account deletion failed")
        return _legal_template(request, "legal/data_deletion.html", title="Data Deletion · LlamaQueue",
                               current_user=user, csrf_token=expected, error="Deletion could not be completed. Please contact Rjmortii@gmail.com.")
    finally:
        db.close()
    request.session.clear()
    return _legal_template(request, "legal/deleted.html", title="Account Deleted · LlamaQueue")


# -------------------------
# Dashboard
# -------------------------

@app.get("/")
def home(request: Request):

    current_user = get_current_user(request)

    queue, registrations, settings, history, moderators, db = get_services(request)

    print("API current user:", get_current_user(request))
    print("API queue:", queue)

    if queue is None:

        creator_settings = {
            "creator_name": "Creator Queue",
            "queue_name": "Creator Queue",
            "party_size": 5,
        }

        status = "🔴 CLOSED"

        current = []

        waiting = []

        history_items = []

        next_lobby = []

        remaining_waiting = 0

        player_names = []

    else:

        print(f"Current user: {current_user.display_name}")

        status = "🟢 OPEN" if queue.is_open() else "🔴 CLOSED"

        creator_settings = settings.get_all()

        queue.set_lobby_size(
            creator_settings["party_size"]
        )

        current = queue.current_lobby()

        waiting = queue.waiting_players()

        history_items = history.get_history()

        next_lobby = waiting[
            :creator_settings["party_size"]
        ]

        remaining_waiting = max(
            0,
            len(waiting) - len(next_lobby)
        )

        player_names = [
            player["player"]
            for player in current
            if player["player"]
        ]

    response = templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "current_user": current_user,
            "settings": creator_settings,

            "status": status,
            "party_size": creator_settings["party_size"],
            "current": current,
            "waiting": len(waiting),
            "history": history_items,
            "player_names": player_names,
            "next_lobby": next_lobby,
            "remaining_waiting": remaining_waiting,
        },
    )

    db.close()

    return response

# -------------------------
# Registration
# -------------------------

from fastapi import Header, Query


def parse_nightbot_header(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        if raw.lstrip().startswith("{"):
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        pass
    try:
        return {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}
    except Exception:
        return {}


@app.get("/nightbot")
async def nightbot(
    request: Request,
    command: str = Query(...),
    player: str | None = Query(None),
    nightbot_channel: str | None = Header(default=None, alias="Nightbot-Channel"),
    nightbot_user: str | None = Header(default=None, alias="Nightbot-User"),
):
    creator_name = request.query_params.get("channel")
    chatter_name = request.query_params.get("user")

    channel = parse_nightbot_header(nightbot_channel)
    chatter = parse_nightbot_header(nightbot_user)
    creator_name = channel.get("name") or channel.get("displayName") or creator_name
    chatter_name = chatter.get("name") or chatter.get("displayName") or chatter_name
    chatter_provider = (chatter.get("provider") or "").lower()
    chatter_provider_id = chatter.get("providerId") or chatter.get("provider_id")

    if not creator_name or not chatter_name:
        return Response(
            content="Missing Nightbot user/channel.",
            media_type="text/plain",
            status_code=400,
        )

    db = SessionLocal()

    try:
        creator = get_creator_from_nightbot(
            db, 
            channel,
            creator_name,
        )

        if creator is None:
            return Response(
                content="Creator account not found.",
                media_type="text/plain",
                status_code=404,
            )

        bot = LlamaBot(creator.id)

        if command == "reg":
            message = f"!reg {player}"
        elif command =="playerid":
            message = "!fc"    
        else:
            message = f"!{command}"

        response = bot.process(
            username=chatter_name,
            message=message,
            chatter_provider=chatter_provider,
            chatter_provider_id=chatter_provider_id,
        )

    finally:
        db.close()

    return Response(
        content=(response.message or ("Joined the queue." if response.success and command == "join" else "OK" if response.success else "Command failed.")),
        media_type="text/plain",
        status_code=200,
    )
    
@app.post("/register")
def register(
    request: Request,
    youtube: str = Form(...),
    player: str = Form(...)
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if registrations is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    registrations.register(youtube, player)

    db.close()

    return RedirectResponse("/", status_code=303)


@app.post("/join")
def join(
    request: Request,
    youtube: str = Form(...)
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    player = registrations.get_player(youtube)

    if player is None:
        player = ""

    queue.join(youtube, player)

    db.close()

    return RedirectResponse("/", status_code=303)


@app.post("/remove")
def remove(
    request: Request,
    name: str = Form(...),
    next: str = Form("/")
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    queue.remove(name)

    db.close()

    return RedirectResponse(
        next,
        status_code=303
    )

# -------------------------
# Queue Moderator Actions
# -------------------------

@app.post("/move/up")
def move_up(
    request: Request,
    name: str = Form(...),
    next: str = Form("/")
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    queue.move_up(name)

    db.close()

    return RedirectResponse(
        next,
        status_code=303
    )


@app.post("/move/down")
def move_down(
    request: Request,
    name: str = Form(...),
    next: str = Form("/")
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    queue.move_down(name)

    db.close()

    return RedirectResponse(
        next,
        status_code=303
    )


@app.post("/move/front")
def move_front(
    request: Request,
    name: str = Form(...),
    next: str = Form("/")
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    queue.move_to_front(name)

    db.close()

    return RedirectResponse(
        next,
        status_code=303
    )

# -------------------------
# Queue Controls
# -------------------------

@app.post("/complete")
def complete(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current = queue.current_lobby()

    if current:
        history.add_lobby(current)

        current_user = get_current_user(request)
        nightbot = NightbotService(current_user)

        names = ", ".join(player["player"] for player in current)

        nightbot.send_message(
            "🎮 Lobby is Launching! • "
            f"Players: {names}. • "
            "Please send your invites!"
        )

    queue.complete_lobby()

    db.close()

    return RedirectResponse("/", status_code=303)


@app.post("/open")
def open_queue(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    queue.open_queue()

    db.close()

    return RedirectResponse("/", status_code=303)


@app.post("/close")
def close_queue(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    queue.close_queue()

    db.close()

    return RedirectResponse("/", status_code=303)

# -------------------------
# Party Size Controls
# -------------------------

@app.post("/party/increase")
def increase_party(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current = settings.get("party_size")
    maximum = settings.get("max_party_size")

    if current < maximum:
        settings.set("party_size", current + 1)

    db.close()

    return RedirectResponse("/", status_code=303)


@app.post("/party/decrease")
def decrease_party(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current = settings.get("party_size")
    minimum = settings.get("min_party_size")

    if current > minimum:
        settings.set("party_size", current - 1)

    db.close()

    return RedirectResponse("/", status_code=303)

# -------------------------
# Queue
# -------------------------

@app.get("/queue")
def queue_page(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)

    creator_settings = settings.get_all()

    queue.set_lobby_size(
        creator_settings["party_size"]
    )

    current = queue.current_lobby()

    waiting = queue.waiting_players()

    for player in waiting:
        player["wait_time"] = queue.waiting_time(player)

    queue_size = len(waiting)

    estimated_wait = (
        queue_size *
        creator_settings["estimated_match_length"]
    )

    current_count = len(current)

    lobby_percent = (
        int((current_count / creator_settings["party_size"]) * 100)
        if creator_settings["party_size"]
        else 0
    )

    lobby_ready = (
        current_count >= creator_settings["party_size"]
    )

    response = templates.TemplateResponse(
        request=request,
        name="queue.html",
        context={
            "title": "Queue",
            "current_user": current_user,
            "settings": creator_settings,

            "current": current,
            "current_count": current_count,
            "waiting": waiting,
            "queue_size": queue_size,
            "estimated_wait": estimated_wait,
            "party_size": creator_settings["party_size"],
            "lobby_percent": lobby_percent,
            "lobby_ready": lobby_ready,
        }
    )

    db.close()

    return response


# -------------------------
@app.get("/history")
def history_page(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if history is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)
    creator_settings = settings.get_all()

    response = templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "title": "History",
            "current_user": current_user,
            "settings": creator_settings,

            "history": history.get_history(),
            "total_lobbies": history.total_lobbies(),
            "players_hosted": history.total_players(),
            "average_players": history.average_players(),
            "latest_lobby": history.latest_lobby(),
        }
    )

    db.close()

    return response


@app.post("/history/delete")
def delete_history(
    request: Request,
    lobby_id: int = Form(...)
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if history is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    history.delete_lobby(lobby_id)

    db.close()

    return RedirectResponse(
        "/history",
        status_code=303
    )

@app.get("/statistics")
def statistics_page(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if history is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)
    creator_settings = settings.get_all()

    stats = history.statistics()

    response = templates.TemplateResponse(
        request=request,
        name="statistics.html",
        context={
            "title": "Statistics",
            "current_user": current_user,
            "settings": creator_settings,

            "stats": stats,
        }
    )

    db.close()

    return response

# -------------------------
# Settings
# -------------------------

@app.get("/nightbot/commands")
def nightbot_commands(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)
    
    command_service = CommandService(db, current_user.id)

    nightbot = NightbotService(current_user)

    try:
        nightbot_commands = nightbot.list_commands()
    except Exception:
        nightbot_commands = []

    response = templates.TemplateResponse(
        request=request,
        name="nightbot_commands.html",
        context={
            "title": "Nightbot Commands",
            "current_user": current_user,
            "settings": settings.get_all(),
            "sync_status": command_service.get_sync_status(
                nightbot_commands
            ),
            "nightbot_commands": nightbot_commands,
            "creator_settings": settings.get_all(),
        },
    )

    db.close()

    return response

@app.post("/nightbot/commands/save")
async def save_nightbot_commands(
    request: Request,
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    form = await request.form()

    ids = [int(x) for x in form.getlist("ids")]

    mappings = (
        db.query(CommandMapping)
        .filter(CommandMapping.id.in_(ids))
        .all()
    )

    mapping_lookup = {
        mapping.id: mapping
        for mapping in mappings
    }

    for mapping_id in ids:

        mapping = mapping_lookup.get(mapping_id)

        if mapping is None:
            continue

        mapping.command = form.get(
            f"command_{mapping_id}",
            mapping.command,
        ).strip()

        mapping.message = form.get(
            f"message_{mapping_id}",
            mapping.message,
        )

        mapping.permission = form.get(
            f"permission_{mapping_id}",
            mapping.permission,
        )

        try:
            mapping.cooldown = int(
                form.get(
                    f"cooldown_{mapping_id}",
                    mapping.cooldown,
                )
            )
        except (TypeError, ValueError):
            pass

        mapping.enabled = (
            form.get(f"enabled_{mapping_id}") == "1"
        )
    settings.update(
        player_id_label=form.get(
            "player_id_label",
            settings.get("player_id_label"),
        ),
        player_id_value=form.get(
            "player_id_value",
            settings.get("player_id_value"),
        ),
    )

    db.commit()
    db.close()

    return RedirectResponse(
        "/nightbot/commands",
        status_code=303,
    )


@app.post("/nightbot/commands/add")
async def add_nightbot_command(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)

    form = await request.form()

    command = form.get("command", "").strip()

    if command and not command.startswith("!"):
        command = "!" + command

    mapping = CommandMapping(
        user_id=current_user.id,
        action=f"custom_{command.lstrip('!')}",
        command=command,
        description=form.get("description", "Custom Command"),
        message=form.get("message", ""),
        permission=form.get("permission", "everyone"),
        cooldown=int(form.get("cooldown", 30)),
        enabled=True,
        builtin=False,
    )

    db.add(mapping)
    db.commit()
    db.close()

    return RedirectResponse(
        "/nightbot/commands",
        status_code=303,
    )

@app.post("/nightbot/commands/delete/{mapping_id}")
def delete_nightbot_command(
    mapping_id: int,
    request: Request,
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)

    mapping = (
        db.query(CommandMapping)
        .filter(CommandMapping.id == mapping_id)
        .first()
    )

    print(f"mapping_id={mapping_id}")
    print(f"user_id={current_user.id}")
    print(f"mapping={mapping}")
    
    if mapping is not None:
        db.delete(mapping)
        db.commit()

    db.close()

    return RedirectResponse(
        "/nightbot/commands",
        status_code=303,
    )
    
@app.post("/nightbot/commands/sync")
def sync_nightbot_commands(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)

    command_service = CommandService(db, current_user.id)
    nightbot = NightbotService(current_user)

    try:
        nightbot_commands = nightbot.list_commands()
        sync_status = command_service.get_sync_status(
            nightbot_commands
        )

        base_url = str(request.base_url).rstrip("/")

        for item in sync_status:

            mapping = item["mapping"]

            # Build the Nightbot message from the stored command template.
            response = mapping.message.format(base_url=base_url)

            if item["status"] == "missing":

                nightbot.create_command(
                    mapping.command,
                    response,
                    mapping.permission,
                    mapping.cooldown,
                )

            elif item["status"] == "update":

                nightbot.update_command(
                    item["nightbot"]["_id"],
                    mapping.command,
                    response,
                    mapping.permission,
                    mapping.cooldown,
                )

    except Exception as ex:

        print(ex)

    db.close()

    return RedirectResponse(
        "/nightbot/commands",
        status_code=303,
    )



@app.get("/settings")
def settings_page(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)

    response = templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "title": "Settings",
            "current_user": current_user,
            "settings": settings.get_all(),
            "priority_settings": PriorityService.get_settings(db, current_user.id),
        }
    )

    db.close()

    return response

@app.post("/settings/save")
def save_settings(
    request: Request,

    creator_name: str = Form(...),
    queue_name: str = Form(...),
    player_label: str = Form(...),

    party_size: int = Form(...),
    min_party_size: int = Form(...),
    max_party_size: int = Form(...),

    estimated_match_length: int = Form(...),

    theme: str = Form(...)
):

    print("=== ENTERED /settings/save ===")

    queue, registrations, settings, history, moderators, db = get_services(request)

    if settings is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    print("Calling settings.update()")

    settings.update(
        creator_name=creator_name,
        queue_name=queue_name,
        player_label=player_label,
        party_size=party_size,
        min_party_size=min_party_size,
        max_party_size=max_party_size,
        estimated_match_length=estimated_match_length,
        theme=theme,
    )

    print("Returned from settings.update()")

    db.close()

    return RedirectResponse(
        "/settings",
        status_code=303
    )



@app.post("/settings/priority")
def save_priority_settings(
    request: Request,
    priority_enabled: str = Form("0"),
    priority_t3: int = Form(1),
    priority_t2: int = Form(2),
    priority_youtube_member: int = Form(3),
    priority_t1: int = Form(4),
):
    current_user = get_current_user(request)
    if current_user is None:
        return RedirectResponse("/login", status_code=302)
    ranks = {
        "twitch_t3": priority_t3,
        "twitch_t2": priority_t2,
        "youtube_member": priority_youtube_member,
        "twitch_t1": priority_t1,
    }
    db = SessionLocal()
    try:
        try:
            saved = PriorityService.save_settings(
                db, current_user.id, priority_enabled == "1", ranks
            )
        except (ValueError, TypeError):
            return RedirectResponse("/settings?priority_error=rank", status_code=303)
        user = db.query(User).filter(User.id == current_user.id).first()
        if user is not None:
            QueueService(db, user).reorder_by_priority(saved["ranks"], saved["enabled"])
    finally:
        db.close()
    return RedirectResponse("/settings?saved=priority", status_code=303)


@app.post("/settings/appearance")
def save_appearance(
    request: Request,
    background_color: str = Form("#101418"),
    surface_color: str = Form("#1B2128"),
    raised_surface_color: str = Form("#252D36"),
    accent_color: str = Form("#33C759"),
    accent_text_color: str = Form("#7BE495"),
    text_color: str = Form("#F4F7F8"),
    muted_text_color: str = Form("#A9B4BE"),
    border_color: str = Form("#2E3742"),
    font_family: str = Form("Segoe UI"),
    font_size: int = Form(16),
    corner_radius: int = Form(14),
    density: str = Form("comfortable"),
):
    import re
    current_user = get_current_user(request)
    if current_user is None:
        return RedirectResponse("/login", status_code=302)

    colors = {
        "background_color": background_color,
        "surface_color": surface_color,
        "raised_surface_color": raised_surface_color,
        "accent_color": accent_color,
        "accent_text_color": accent_text_color,
        "text_color": text_color,
        "muted_text_color": muted_text_color,
        "border_color": border_color,
    }
    if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", value or "") for value in colors.values()):
        return RedirectResponse("/settings?appearance_error=color", status_code=303)

    allowed_fonts = {"Segoe UI", "Arial", "Verdana", "Tahoma", "Georgia", "Trebuchet MS", "Courier New"}
    if font_family not in allowed_fonts or density not in {"compact", "comfortable", "spacious"}:
        return RedirectResponse("/settings?appearance_error=choice", status_code=303)

    db = SessionLocal()
    try:
        appearance = db.query(UserAppearance).filter_by(user_id=current_user.id).first()
        if appearance is None:
            appearance = UserAppearance(user_id=current_user.id)
            db.add(appearance)
        for key, value in colors.items():
            setattr(appearance, key, value.upper())
        appearance.font_family = font_family
        appearance.font_size = max(13, min(21, int(font_size)))
        appearance.corner_radius = max(6, min(28, int(corner_radius)))
        appearance.density = density
        db.commit()
    finally:
        db.close()
    return RedirectResponse("/settings?saved=appearance", status_code=303)



# -------------------------
# Website appearance presets (Save 1 / Save 2 / Save 3)
# -------------------------

APPEARANCE_PRESET_FIELDS = (
    "background_color", "surface_color", "raised_surface_color", "accent_color",
    "accent_text_color", "text_color", "muted_text_color", "border_color",
    "font_family", "font_size", "corner_radius", "density",
)
APPEARANCE_DEFAULTS = {
    "background_color": "#101418", "surface_color": "#1B2128",
    "raised_surface_color": "#252D36", "accent_color": "#33C759",
    "accent_text_color": "#7BE495", "text_color": "#F4F7F8",
    "muted_text_color": "#A9B4BE", "border_color": "#2E3742",
    "font_family": "Segoe UI", "font_size": 16, "corner_radius": 14,
    "density": "comfortable",
}


def _appearance_values_from_form(payload):
    import re
    values = {key: payload.get(key, APPEARANCE_DEFAULTS[key]) for key in APPEARANCE_PRESET_FIELDS}
    color_keys = APPEARANCE_PRESET_FIELDS[:8]
    if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", str(values[key]) or "") for key in color_keys):
        raise ValueError("One or more colors are invalid.")
    if values["font_family"] not in {"Segoe UI", "Arial", "Verdana", "Tahoma", "Georgia", "Trebuchet MS", "Courier New"}:
        raise ValueError("Font family is invalid.")
    if values["density"] not in {"compact", "comfortable", "spacious"}:
        raise ValueError("Interface spacing is invalid.")
    values["font_size"] = max(13, min(21, int(values["font_size"])))
    values["corner_radius"] = max(6, min(28, int(values["corner_radius"])))
    for key in color_keys:
        values[key] = str(values[key]).upper()
    return values


@app.get("/api/appearance-presets")
def list_appearance_presets(request: Request):
    current_user = get_current_user(request)
    if current_user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    db = SessionLocal()
    try:
        rows = db.query(AppearancePreset).filter_by(user_id=current_user.id).all()
        saved = {row.slot: row for row in rows}
        return JSONResponse({"slots": [
            {"slot": slot, "saved": slot in saved,
             "name": saved[slot].name if slot in saved else "",
             "updated_at": saved[slot].updated_at.isoformat() if slot in saved and saved[slot].updated_at else None}
            for slot in (1, 2, 3)
        ]})
    finally:
        db.close()


@app.post("/api/appearance-presets/{slot}/save")
async def save_appearance_preset(slot: int, request: Request):
    current_user = get_current_user(request)
    if current_user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    if slot not in (1, 2, 3):
        return JSONResponse({"error": "Choose preset 1, 2, or 3."}, status_code=400)
    try:
        payload = await request.json()
        values = _appearance_values_from_form(payload)
    except Exception as exc:
        return JSONResponse({"error": str(exc) or "Invalid appearance values."}, status_code=400)
    db = SessionLocal()
    try:
        row = db.query(AppearancePreset).filter_by(user_id=current_user.id, slot=slot).first()
        if row is None:
            row = AppearancePreset(user_id=current_user.id, slot=slot)
            db.add(row)
        row.name = str(payload.get("name") or f"Appearance {slot}")[:80]
        row.settings_json = json.dumps(values, separators=(",", ":"))
        db.commit()
        return JSONResponse({"ok": True, "slot": slot, "name": row.name})
    finally:
        db.close()


@app.post("/api/appearance-presets/{slot}/load")
def load_appearance_preset(slot: int, request: Request):
    current_user = get_current_user(request)
    if current_user is None:
        return JSONResponse({"error": "Authentication required"}, status_code=401)
    if slot not in (1, 2, 3):
        return JSONResponse({"error": "Choose preset 1, 2, or 3."}, status_code=400)
    db = SessionLocal()
    try:
        row = db.query(AppearancePreset).filter_by(user_id=current_user.id, slot=slot).first()
        if row is None:
            return JSONResponse({"error": f"Appearance {slot} is empty."}, status_code=404)
        try:
            values = _appearance_values_from_form(json.loads(row.settings_json))
        except Exception:
            return JSONResponse({"error": "This saved appearance is invalid."}, status_code=400)
        appearance = db.query(UserAppearance).filter_by(user_id=current_user.id).first()
        if appearance is None:
            appearance = UserAppearance(user_id=current_user.id)
            db.add(appearance)
        for key, value in values.items():
            setattr(appearance, key, value)
        db.commit()
        return JSONResponse({"ok": True, "slot": slot, "name": row.name})
    finally:
        db.close()


@app.post("/settings/appearance/reset")
def reset_appearance(request: Request):
    current_user = get_current_user(request)
    if current_user is None:
        return RedirectResponse("/login", status_code=302)
    db = SessionLocal()
    try:
        appearance = db.query(UserAppearance).filter_by(user_id=current_user.id).first()
        if appearance is not None:
            db.delete(appearance)
            db.commit()
    finally:
        db.close()
    return RedirectResponse("/settings?saved=reset", status_code=303)

@app.post("/test_queue")
def populate_test_queue(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    players = [
        ("RyanStone", "LlamaRyan"),
        ("PocketPlays42", "PocketJon"),
        ("RockStarYT", "LoisRockstar"),
        ("Southernman3050", "Southernman"),
        ("BadLuck", "BadLuck"),
        ("Roman_General75", "Roman"),
        ("AirBrake", "AirBrake"),
        ("Terminal", "Terminal"),
        ("Darc", "Darc"),
        ("SirPocketTheGreat", "SirPocket"),
        ("LlamaFan1", "Steve"),
        ("LlamaFan2", "Alex"),
    ]

    existing = {
        player["youtube"]
        for player in queue.current_lobby() + queue.waiting_players()
    }

    for youtube, player in players:
        if youtube not in existing:
            queue.join(youtube, player)

    db.close()

    return RedirectResponse("/", status_code=303)

# -------------------------
# Moderators
# -------------------------

@app.get("/moderators")
def moderators_page(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if moderators is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    current_user = get_current_user(request)

    response = templates.TemplateResponse(
        request=request,
        name="moderators.html",
        context={
            "title": "Moderators",
            "current_user": current_user,
            "settings": settings.get_all(),
            "moderators": moderators.get_all(),
            "count": moderators.count(),
        }
    )

    db.close()

    return response

@app.post("/moderators/add")
def add_moderator(
    request: Request,
    youtube_name: str = Form(...)
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if moderators is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    moderators.add(youtube_name)

    db.close()

    return RedirectResponse("/moderators", status_code=303)

@app.post("/moderators/delete")
def delete_moderator(
    request: Request,
    youtube_name: str = Form(...)
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if moderators is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    moderators.remove(youtube_name)

    db.close()

    return RedirectResponse("/moderators", status_code=303)   

@app.post("/moderators/update")
def update_moderator(
    request: Request,

    youtube_name: str = Form(...),

    can_open_queue: bool = Form(False),
    can_close_queue: bool = Form(False),
    can_launch_lobby: bool = Form(False),
    can_remove_players: bool = Form(False),
    can_manage_registrations: bool = Form(False),
    can_manage_members: bool = Form(False),
    can_manage_moderators: bool = Form(False),
    can_edit_settings: bool = Form(False),
):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if moderators is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    moderators.update_permissions(
        youtube_name,

        can_open_queue=can_open_queue,
        can_close_queue=can_close_queue,
        can_launch_lobby=can_launch_lobby,
        can_remove_players=can_remove_players,

        can_manage_registrations=can_manage_registrations,
        can_manage_members=can_manage_members,
        can_manage_moderators=can_manage_moderators,
        can_edit_settings=can_edit_settings,
    )

    db.close()

    return RedirectResponse("/moderators", status_code=303)

# -------------------------
# API
# -------------------------

@app.get("/api/dashboard")
def api_dashboard(request: Request):

    queue, registrations, settings, history, moderators, db = get_services(request)

    if queue is None:
        db.close()
        return JSONResponse(
            {"error": "Not logged in"},
            status_code=401
        )

    creator_settings = settings.get_all()

    queue.set_lobby_size(
        creator_settings["party_size"]
    )

    current = queue.current_lobby()
    waiting = queue.waiting_players()

    next_party = waiting[
        :creator_settings["party_size"]
    ]

    remaining_waiting = max(
        0,
        len(waiting) - len(next_party)
    )

    player_names = [
        player["player"]
        for player in current
        if player["player"]
    ]

    response = JSONResponse({
        "status": queue.is_open(),
        "party_size": creator_settings["party_size"],
        "current": current,
        "next": next_party,
        "waiting": len(waiting),
        "remaining_waiting": remaining_waiting,
        "player_names": player_names,
        "history": history.get_history()
    })

    db.close()

    return response