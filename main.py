from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse

from queue_manager import QueueManager
from registration_manager import RegistrationManager

app = FastAPI()

queue = QueueManager()
registrations = RegistrationManager()


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


@app.get("/style.css")
def css():
    return FileResponse("style.css")


@app.get("/", response_class=HTMLResponse)
def home():

    status = "🟢 OPEN" if queue.is_open() else "🔴 CLOSED"

    html = f"""
<!DOCTYPE html>
<html>
<head>
<title>Llama Queue</title>
<link rel="stylesheet" href="/style.css">
</head>

<body>

<div class="container">

<h1>🦙 Llama Queue</h1>

<div class="card">

<h2>Host Controls</h2>

<p><strong>Queue:</strong> {status}</p>
<p><strong>Lobby Size:</strong> {queue.get_lobby_size()}</p>

<form action="/open" method="post" style="display:inline;">
<button>🟢 Open</button>
</form>

<form action="/close" method="post" style="display:inline;">
<button>🔴 Close</button>
</form>

<form action="/lobby/5" method="post" style="display:inline;">
<button>👥 5</button>
</form>

<form action="/lobby/10" method="post" style="display:inline;">
<button>👥 10</button>
</form>

<form action="/complete" method="post" style="display:inline;">
<button>🚀 Complete Lobby</button>
</form>

</div>

<div class="card">

<h2>Register Trainer</h2>

<form action="/register" method="post">

<input
type="text"
name="youtube"
placeholder="YouTube Name"
required>

<br><br>

<input
type="text"
name="trainer"
placeholder="Trainer Name"
required>

<br><br>

<button>Register</button>

</form>

</div>

<div class="card">

<h2>Add Player (Testing)</h2>

<form action="/join" method="post">

<input
type="text"
name="youtube"
placeholder="YouTube Name"
required>

<button>Join Queue</button>

</form>

</div>

<div class="card">

<h2>Current Lobby</h2>
"""

    current = queue.current_lobby()

    if not current:
        html += "<p>No players.</p>"

    for player in current:

        html += f"""
<div class="player-card">

<div class="player-info">

<h2>🦙 {player["youtube"]}</h2>

<p>🎮 Trainer: {player["trainer"] or "Not Set"}</p>

<p class="status">🟢 Waiting</p>

<p class="wait">⏳ Est. Wait: Now</p>

</div>

</div>
"""

    html += """
<form action="/complete" method="post">
<button>🚀 Complete Lobby</button>
</form>

</div>

<div class="card">

<h2>Waiting Trainers</h2>
"""

    waiting = queue.waiting_players()

    if not waiting:
        html += "<p>No one waiting.</p>"

    for index, player in enumerate(waiting):

        html += f"""
<div class="player-card">

<div class="player-info">

<h2>🦙 {player["youtube"]}</h2>

<p>🎮 Trainer: {player["trainer"] or "Not Set"}</p>

<p class="status">🟢 Waiting</p>

<p class="wait">
⏳ Est. Wait:
{queue.estimated_wait(index + queue.get_lobby_size())}
</p>

</div>

<form action="/remove" method="post">

<input
type="hidden"
name="name"
value="{player["youtube"]}">

<button class="remove">❌</button>

</form>

</div>
"""

    html += """
</div>

</div>

</body>
</html>
"""

    return HTMLResponse(content=html)


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