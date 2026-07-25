import os
import json

from dotenv import load_dotenv

# Load environment variables BEFORE importing anything that uses them.
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
from database.models import User
from database.models import CommandMapping
from database.session import Base, engine, SessionLocal

from services.history_service import HistoryService
from services.moderator_service import ModeratorService
from routers.auth import router as auth_router

from services.command_service import CommandService
from services.nightbot_service import NightbotService
from services.queue_service import QueueService
from services.registration_service import RegistrationService
from services.settings_service import SettingsService
from typing import List
from bot import LlamaBot

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET"),
)


app.include_router(auth_router)

Base.metadata.create_all(bind=engine)


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

templates = Jinja2Templates(
    directory="templates",
    context_processors=[
        lambda request: {
            "current_user": get_current_user(request),
        }
    ],
)

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

    if nightbot_channel:
        try:
            creator_name = json.loads(nightbot_channel)["name"]
        except Exception:
            pass

    if nightbot_user:
        try:
            chatter_name = json.loads(nightbot_user)["name"]
        except Exception:
            pass

    if not creator_name or not chatter_name:
        return Response(
            content="Missing Nightbot user/channel.",
            media_type="text/plain",
            status_code=400,
        )

    bot = LlamaBot(creator_name)

    if command == "reg":
        message = f"!reg {player}"
    else:
        message = f"!{command}"

    response = bot.process(
        username=chatter_name,
        message=message,
    )

    return Response(
        content=response.message,
        media_type="text/plain",
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
# History
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