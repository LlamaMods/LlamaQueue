from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi import FastAPI, Form
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    JSONResponse,
)

from lobby_history_manager import LobbyHistoryManager
from queue_manager import QueueManager
from registration_manager import RegistrationManager
from profile_manager import ProfileManager
from settings_manager import SettingsManager

app = FastAPI()


app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

queue = QueueManager()
registrations = RegistrationManager()
history = LobbyHistoryManager()
profile = ProfileManager()
settings = SettingsManager()
templates = Jinja2Templates(
    directory="templates",
    context_processors=[
        lambda request: {
            "settings": settings.get_all()
        }
    ]
)


# -------------------------
# Demo Players
# -------------------------

queue.join("Ryan", "LlamaRyan")
queue.join("Pocket", "PocketJon")
queue.join("Rockstar", "LoisRockstar")
queue.join("BadLuck", "BadLuck")
queue.join("AirBrake", "AirBrake")
queue.join("Southern", "Southern")
queue.join("Roman", "Roman")
queue.join("Steve", "Steve")
queue.join("Sarah", "Sarah")


# -------------------------
# Dashboard
# -------------------------

@app.get("/")
def home(request: Request):

    status = "🟢 OPEN" if queue.is_open() else "🔴 CLOSED"

    creator_settings = settings.get_all()

    # Keep QueueManager in sync with the selected party size
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

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
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


# -------------------------
# Registration
# -------------------------

@app.post("/register")
def register(
    youtube: str = Form(...),
    player: str = Form(...)
):
    registrations.register(youtube, player)
    return RedirectResponse("/", status_code=303)


@app.post("/join")
def join(youtube: str = Form(...)):

    player = registrations.get_player(youtube)

    if player is None:
        player = ""

    queue.join(youtube, player)

    return RedirectResponse("/", status_code=303)


@app.post("/remove")
def remove(
    name: str = Form(...),
    next: str = Form("/")
):

    queue.remove(name)

    return RedirectResponse(
        next,
        status_code=303
    )


# -------------------------
# Queue Moderator Actions
# -------------------------

@app.post("/move/up")
def move_up(
    name: str = Form(...),
    next: str = Form("/")
):

    queue.move_up(name)

    return RedirectResponse(
        next,
        status_code=303
    )


@app.post("/move/down")
def move_down(
    name: str = Form(...),
    next: str = Form("/")
):

    queue.move_down(name)

    return RedirectResponse(
        next,
        status_code=303
    )


@app.post("/move/front")
def move_front(
    name: str = Form(...),
    next: str = Form("/")
):

    queue.move_to_front(name)

    return RedirectResponse(
        next,
        status_code=303
    )


# -------------------------
# Queue Controls
# -------------------------

@app.post("/complete")
def complete():

    current = queue.current_lobby()

    if current:
        history.add_lobby(current)

    queue.complete_lobby()

    return RedirectResponse("/", status_code=303)


@app.post("/open")
def open_queue():
    queue.open_queue()
    return RedirectResponse("/", status_code=303)


@app.post("/close")
def close_queue():
    queue.close_queue()
    return RedirectResponse("/", status_code=303)


# -------------------------
# Party Size Controls
# -------------------------

@app.post("/party/increase")
def increase_party():

    current = settings.get("party_size")
    maximum = settings.get("max_party_size")

    if current < maximum:
        settings.set("party_size", current + 1)

    return RedirectResponse("/", status_code=303)


@app.post("/party/decrease")
def decrease_party():

    current = settings.get("party_size")
    minimum = settings.get("min_party_size")

    if current > minimum:
        settings.set("party_size", current - 1)

    return RedirectResponse("/", status_code=303)

# -------------------------
# Queue
# -------------------------

@app.get("/queue")
def queue_page(request: Request):

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

    lobby_percent = int(
        (current_count / creator_settings["party_size"]) * 100
    ) if creator_settings["party_size"] else 0

    lobby_ready = (
        current_count >= creator_settings["party_size"]
    )

    return templates.TemplateResponse(
        request=request,
        name="queue.html",
        context={
            "title": "Queue",

            "current": current,
            "current_count": current_count,

            "waiting": waiting,

            "queue_size": queue_size,

            "estimated_wait": estimated_wait,

            "party_size": creator_settings["party_size"],

            "lobby_percent": lobby_percent,
            "lobby_ready": lobby_ready
        }
    )

# -------------------------
# History
# -------------------------

@app.get("/history")
def history_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "title": "History",

            "history": history.get_history(),

            "total_lobbies": history.total_lobbies(),

            "players_hosted": history.total_players(),

            "average_players": history.average_players(),

            "latest_lobby": history.latest_lobby(),
        }
    )

@app.post("/history/delete")
def delete_history(
    index: int = Form(...)
):

    history.delete_lobby(index)

    return RedirectResponse(
        "/history",
        status_code=303
    )

@app.get("/statistics")
def statistics_page(request: Request):

    stats = history.statistics()

    return templates.TemplateResponse(
        request=request,
        name="statistics.html",
        context={
            "title": "Statistics",
            "stats": stats
        }
    )

# -------------------------
# Settings
# -------------------------

@app.get("/settings")
def settings_page(request: Request):


    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "title": "Settings",
            
        }
    )


@app.post("/settings/save")
def save_settings(

    creator_name: str = Form(...),
    queue_name: str = Form(...),
    player_label: str = Form(...),

    party_size: int = Form(...),
    min_party_size: int = Form(...),
    max_party_size: int = Form(...),

    estimated_match_length: int = Form(...),

    theme: str = Form(...)

):

    settings.set("creator_name", creator_name)
    settings.set("queue_name", queue_name)
    settings.set("player_label", player_label)

    settings.set("party_size", party_size)
    settings.set("min_party_size", min_party_size)
    settings.set("max_party_size", max_party_size)

    settings.set(
        "estimated_match_length",
        estimated_match_length
    )

    settings.set("theme", theme)

    return RedirectResponse(
        "/settings",
        status_code=303
    )


# -------------------------
# API
# -------------------------

@app.get("/api/dashboard")
def api_dashboard():

    creator_settings = settings.get_all()

    # Keep QueueManager in sync
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

    return JSONResponse({

        "status": queue.is_open(),

        "party_size": creator_settings["party_size"],

        "current": current,

        "next": next_party,

        "waiting": len(waiting),

        "remaining_waiting": remaining_waiting,

        "player_names": player_names,

        "history": history.get_history()

    })