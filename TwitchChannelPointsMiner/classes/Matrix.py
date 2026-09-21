from textwrap import dedent

import logging
import requests
from urllib.parse import quote

from TwitchChannelPointsMiner.classes.Settings import Events


class Matrix(object):
    __slots__ = ["access_token", "homeserver", "room_id", "events"]

    def __init__(self, username: str, password: str, homeserver: str, room_id: str, events: list):
        self.homeserver = homeserver
        self.room_id = quote(room_id, safe="!:")
        self.events = {str(e) for e in events}
        self.access_token = None

        try:
            response = requests.post(
                url=f"https://{self.homeserver}/_matrix/client/r0/login",
                json={
                    "user": username,
                    "password": password,
                    "type": "m.login.password"
                },
                timeout=10,
            )
            if response.status_code == 200:
                self.access_token = response.json().get("access_token")
        except (requests.RequestException, ValueError):
            pass

        if not self.access_token:
            logging.getLogger(__name__).info("Invalid Matrix password provided. Notifications will not be sent.")

    def send(self, message: str, event: Events) -> None:
        if not self.access_token:
            return
        if str(event) in self.events:
            try:
                requests.post(
                    url=f"https://{self.homeserver}/_matrix/client/r0/rooms/{self.room_id}/send/m.room.message",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    json={
                        "body": dedent(message),
                        "msgtype": "m.text"
                    },
                    timeout=10,
                )
            except requests.RequestException:
                pass
