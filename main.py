from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from lobby_history_manager import LobbyHistoryManager
from queue_manager import QueueManager
from registration_manager import RegistrationManager
from profile_manager import ProfileManager

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


# Demo Players
queue.join("Ryan", "LlamaRyan")
queue.join("Pocket", "PocketJon")
queue.join("Rockstar", "LoisRockstar")
queue.join("BadLuck", "BadLuck")
queue.join("AirBrake", "AirBrake")
queue.join("Southern", "Southern")
queue.join("Roman", "Roman")
queue.join("Steve", "Steve")
queue.join("Sarah", "Sarah")



@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    status = "🟢 OPEN" if queue.is_open() else "🔴 CLOSED"

    current = queue.current_lobby()
    waiting = queue.waiting_players()
    history_items = history.get_history()

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
    "lobby_size": queue.get_lobby_size(),
    "current": current,
    "waiting": waiting,
    "history": history_items,
    "trainer_names": trainer_names,
    "profile": profile.load(),
}
)


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


@app.post("/complete")
def complete():

    current = queue.current_lobby()

    if current:
        history.add_lobby(current)

    queue.complete_lobby()

    return RedirectResponse("/", status_code=303)

@app.post("/lobby/5")
def lobby5():
    queue.set_lobby_size(5)
    return RedirectResponse("/", status_code=303)


@app.post("/lobby/10")
def lobby10():
    queue.set_lobby_size(10)
    return RedirectResponse("/", status_code=303)


@app.post("/open")
def open_queue():
    queue.open_queue()
    return RedirectResponse("/", status_code=303)


@app.post("/close")
def close_queue():
    queue.close_queue()
    return RedirectResponse("/", status_code=303)

