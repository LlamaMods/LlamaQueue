import os
import pickle

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class YouTubeManager:

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.force-ssl"
    ]

    def __init__(self):

        self.credentials_folder = "credentials"

        self.client_secret = os.path.join(
            self.credentials_folder,
            "client_secret.json"
        )

        self.token_file = os.path.join(
            self.credentials_folder,
            "token.pickle"
        )

        self.credentials = None
        self.youtube = None

        self.channel_id = None
        self.channel_title = None

        self.broadcast = None
        self.broadcast_id = None
        self.live_chat_id = None

    # ------------------------------------
    # OAuth
    # ------------------------------------

    def authenticate(self):

        if os.path.exists(self.token_file):

            with open(self.token_file, "rb") as token:
                self.credentials = pickle.load(token)

        if (
            self.credentials
            and self.credentials.expired
            and self.credentials.refresh_token
        ):

            self.credentials.refresh(Request())

        elif (
            self.credentials is None
            or not self.credentials.valid
        ):

            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secret,
                self.SCOPES
            )

            self.credentials = flow.run_local_server(
                port=0
            )

            with open(self.token_file, "wb") as token:
                pickle.dump(
                    self.credentials,
                    token
                )

        self.youtube = build(
            "youtube",
            "v3",
            credentials=self.credentials
        )

        return self.youtube

    # ------------------------------------
    # Connect
    # ------------------------------------

    def connect(self):

        if self.youtube is None:
            self.authenticate()

        request = self.youtube.channels().list(
            part="snippet",
            mine=True
        )

        response = request.execute()

        items = response.get("items", [])

        if not items:
            raise Exception(
                "No YouTube channel found."
            )

        channel = items[0]

        self.channel_id = channel["id"]
        self.channel_title = channel["snippet"]["title"]

        print()
        print("🦙 Connected to YouTube!")
        print(f"Channel: {self.channel_title}")
        print(f"Channel ID: {self.channel_id}")
        print()

        return True

    # ------------------------------------
    # Active Broadcast
    # ------------------------------------

    def find_active_broadcast(self):

        if self.youtube is None:
            self.authenticate()

        try:

            request = self.youtube.liveBroadcasts().list(
                part="id,snippet,status",
                mine=True,
                broadcastType="all"
            )

            response = request.execute()

        except HttpError as error:

            print()
            print("YouTube API Error")
            print(error)
            print()

            raise

        items = response.get("items", [])

        if not items:

            self.broadcast = None
            self.broadcast_id = None
            self.live_chat_id = None

            return False

        active = None

        for broadcast in items:

            status = broadcast.get("status", {})

            if status.get("lifeCycleStatus") == "live":

                active = broadcast
                break

        if active is None:

            self.broadcast = None
            self.broadcast_id = None
            self.live_chat_id = None

            return False

        self.broadcast = active
        self.broadcast_id = active["id"]

        snippet = active.get("snippet", {})
        self.live_chat_id = snippet.get("liveChatId")

        print()
        print("🔴 Active livestream found")
        print(f"Broadcast ID: {self.broadcast_id}")
        print(f"Live Chat ID: {self.live_chat_id}")
        print()

        return True
        
    # ------------------------------------
    # Helper Functions
    # ------------------------------------

    def is_live(self):

        return self.find_active_broadcast()
    def get_live_chat_id(self):

        if self.live_chat_id is None:

            self.find_active_broadcast()

        return self.live_chat_id

    def get_broadcast_id(self):

        if self.broadcast_id is None:

            self.find_active_broadcast()

        return self.broadcast_id

    def refresh(self):

        return self.find_active_broadcast()

    # ------------------------------------
    # Send Message
    # ------------------------------------

    def send_message(self, message):

        if self.live_chat_id is None:

            if not self.find_active_broadcast():
                raise Exception(
                    "No active livestream found."
                )

        try:

            request = self.youtube.liveChatMessages().insert(
                part="snippet",
                body={
                    "snippet": {
                        "liveChatId": self.live_chat_id,
                        "type": "textMessageEvent",
                        "textMessageDetails": {
                            "messageText": message
                        }
                    }
                }
            )

            return request.execute()

        except HttpError as error:

            print()
            print("Unable to send YouTube message.")
            print(error)
            print()

            raise

    # ------------------------------------
    # Read Messages
    # ------------------------------------

    def get_messages(self, page_token=None):

        if self.live_chat_id is None:

            if not self.find_active_broadcast():
                raise Exception(
                    "No active livestream found."
                )

        request = self.youtube.liveChatMessages().list(
            liveChatId=self.live_chat_id,
            part="id,snippet,authorDetails",
            pageToken=page_token
        )

        response = request.execute()

        messages = []

        for item in response.get("items", []):

            author = item["authorDetails"][
                "displayName"
            ]

            text = item["snippet"][
                "displayMessage"
            ]

            messages.append({
                "id": item["id"],
                "author": author,
                "message": text
            })

        next_page = response.get(
            "nextPageToken"
        )

        poll_interval = response.get(
            "pollingIntervalMillis",
            1000
        )

        return (
            messages,
            next_page,
            poll_interval
        )
            # ------------------------------------
    # Listen for Chat Messages
    # ------------------------------------

    def listen(self, callback):

        if self.live_chat_id is None:

            if not self.find_active_broadcast():

                raise Exception(
                    "No active livestream found."
                )

        page_token = None
        seen_messages = set()

        print()
        print("🦙 Listening for YouTube chat...")
        print()

        while True:

            try:

                messages, page_token, interval = (
                    self.get_messages(page_token)
                )

                for message in messages:

                    if message["id"] in seen_messages:
                        continue

                    seen_messages.add(
                        message["id"]
                    )

                    callback(
                        message["author"],
                        message["message"]
                    )

                # Prevent the cache from growing forever
                if len(seen_messages) > 5000:

                    seen_messages.clear()

                import time
                time.sleep(interval / 1000)

            except HttpError as error:

                print()
                print("YouTube API Error while reading chat.")
                print(error)
                print("Retrying in 5 seconds...")
                print()

                import time
                time.sleep(5)

                try:

                    self.refresh()

                    page_token = None

                except Exception:

                    time.sleep(5)

            except KeyboardInterrupt:

                print()
                print("🦙 Bot stopped.")
                break

            except Exception as error:

                print()
                print("Unexpected error:")
                print(error)
                print("Retrying in 5 seconds...")
                print()

                import time
                time.sleep(5)