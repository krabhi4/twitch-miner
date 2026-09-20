import logging
import requests

from TwitchChannelPointsMiner.classes.Settings import Events

logger = logging.getLogger(__name__)


class Webhook(object):
    __slots__ = ["endpoint", "method", "events", "timeout"]

    def __init__(self, endpoint: str, method: str, events: list, timeout: int = 1):
        self.endpoint = endpoint
        self.method = method
        self.events = [str(e) for e in events]
        self.timeout = timeout

    def send(self, message: str, event: Events) -> None:
        if str(event) in self.events:
            try:
                data = {
                    "event_name": str(event),
                    "message": message
                }
                if self.method.lower() == "get":
                    requests.get(url=self.endpoint, params=data, timeout=self.timeout)
                elif self.method.lower() == "post":
                    requests.post(url=self.endpoint, data=data, timeout=self.timeout)
                else:
                    raise ValueError("Invalid method, use POST or GET")
            except requests.exceptions.Timeout:
                logger.error(f"Webhook timeout: {self.endpoint} did not respond within {self.timeout} seconds")
