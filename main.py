import os

from dotenv import load_dotenv

# Load environment variables BEFORE importing anything that uses them.
load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from auth.dependencies import get_current_user
from auth.google import oauth
from database.models import User
from database.session import Base, engine, SessionLocal

from services.history_service import HistoryService
from routers.auth import router as auth_router

from services.queue_service import QueueService
from services.registration_service import RegistrationService
from services.settings_service import SettingsService

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
        return None, None, None, None, db

    user = (
        db.query(User)
        .filter(User.id == current_user.id)
        .first()
    )

    queue = QueueService(db, user)
    registrations = RegistrationService(db, user)
    settings = SettingsService(db, user)
    history = HistoryService(db, user)

    return queue, registrations, settings, history, db

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

    queue, registrations, settings, history, db = get_services(request)

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

@app.post("/register")
def register(
    request: Request,
    youtube: str = Form(...),
    player: str = Form(...)
):

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

    if queue is None:
        db.close()
        return RedirectResponse("/login", status_code=302)

    queue.open_queue()

    db.close()

    return RedirectResponse("/", status_code=303)


@app.post("/close")
def close_queue(request: Request):

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

@app.get("/settings")
def settings_page(request: Request):

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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

    queue, registrations, settings, history, db = get_services(request)

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
# API
# -------------------------

@app.get("/api/dashboard")
def api_dashboard(request: Request):

    queue, registrations, settings, history, db = get_services(request)

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