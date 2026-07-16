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

templates = Jinja2Templates(directory="templates")

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
    queue.set_lobby_size(creator_settings["party_size"])

    current = queue.current_lobby()
    waiting = queue.waiting_players()
    history_items = history.get_history()

    next_lobby = waiting[:creator_settings["party_size"]]

    remaining_waiting = max(
        0,
        len(waiting) - len(next_lobby)
    )

    trainer_names = [
        player["trainer"]
        for player in current
        if player["trainer"]
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
            "trainer_names": trainer_names,
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
    trainer: str = Form(...)
):
    registrations.register(youtube, trainer)
    return RedirectResponse("/", status_code=303)


@app.post("/join")
def join(youtube: str = Form(...)):

    trainer = registrations.get_trainer(youtube)

    if trainer is None:
        trainer = ""

    queue.join(youtube, trainer)

    return RedirectResponse("/", status_code=303)


@app.post("/remove")
def remove(name: str = Form(...)):
    queue.remove(name)
    return RedirectResponse("/", status_code=303)


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
# Settings
# -------------------------

@app.get("/settings")
def settings_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "title": "Settings",
            "settings": settings.get_all()
        }
    )


@app.post("/settings/save")
def save_settings(

    party_size: int = Form(...),
    min_party_size: int = Form(...),
    max_party_size: int = Form(...)

):

    settings.set("party_size", party_size)
    settings.set("min_party_size", min_party_size)
    settings.set("max_party_size", max_party_size)

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

    trainer_names = [
        player["trainer"]
        for player in current
        if player["trainer"]
    ]

    return JSONResponse({

        "status": queue.is_open(),

        "party_size": creator_settings["party_size"],

        "current": current,

        "next": next_party,

        "waiting": len(waiting),

        "remaining_waiting": remaining_waiting,

        "trainer_names": trainer_names,

        "history": history.get_history()

    })