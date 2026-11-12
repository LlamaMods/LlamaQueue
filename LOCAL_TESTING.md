# LlamaQueue local testing

## Start the test build without OAuth login

1. Extract this ZIP into a new folder. Do not overwrite your original LlamaQueue folder.
2. In the project root (the folder containing `main.py`), create a new file named `.env`. **Do not copy your production `.env` wholesale.**
3. Put these settings in the new local `.env`:

   ```env
   SESSION_SECRET=replace-this-with-a-random-secret-at-least-32-characters-long
   LLAMAQUEUE_LOCAL_TEST_MODE=1
   DB_PATH=database/llamaqueue-local-test.db
   ```

   Generate a strong local session secret in CMD with: `python -c "import secrets; print(secrets.token_urlsafe(48))"` and paste the result after `SESSION_SECRET=`.
4. Install dependencies in your virtual environment: `python -m pip install -r requirements.txt`
5. Run the app from the project root: `uvicorn main:app --reload`
6. Open `http://127.0.0.1:8000`. A separate `Local Test User` and isolated local database are created automatically.
7. Open **Unified Chat**, use **Preview sample chat**, and customize the feed. Save appearance settings, then open the generated OBS overlay URL to check the result.

## Important safety boundary

- The bypass requires the explicit environment switch, a loopback hostname, and a loopback client connection. It will not activate on Render or a public network connection.
- Never add `LLAMAQUEUE_LOCAL_TEST_MODE=1` to Render. Remove it from your local `.env` when testing is finished.
- Do not copy your production database path into the test `.env`; the example above creates a separate database.
- Local preview mode is for UI/customization testing. Connect Twitch and YouTube on your existing Render site for live messages. The chat flow reuses the existing Google and Twitch callback routes, so **do not add, remove, or change any callback URLs** in either provider console.
- The OBS overlay URL is a private bearer URL. Anyone who has it can view that account's chat; keep it private.

## Appearance options

Theme (transparent/dark/light), font family, font size, background color and opacity, message text and username colors, Twitch and YouTube accent colors, message count, spacing, corner radius, platform icons, timestamps, usernames, and available badges. Settings are saved per account and shared by the dashboard and OBS overlay.
