import json

from TwitchChannelPointsMiner.utils import server_time


class Message(object):
    __slots__ = [
        "topic",
        "topic_user",
        "message",
        "type",
        "data",
        "timestamp",
        "channel_id",
        "identifier",
    ]

    def __init__(self, data):
        topic_parts = data.get("topic", "").split(".", 1)
        self.topic = topic_parts[0]
        self.topic_user = topic_parts[1] if len(topic_parts) > 1 else ""

        msg = data.get("message", "{}")
        if isinstance(msg, dict):
            self.message = msg
        else:
            try:
                self.message = json.loads(msg)
            except (json.JSONDecodeError, TypeError):
                self.message = {}

        self.type = self.message.get("type", "")
        self.data = self.message.get("data") if isinstance(self.message, dict) else None

        self.timestamp = self.__get_timestamp()
        self.channel_id = self.__get_channel_id()

        self.identifier = f"{self.type}.{self.topic}.{self.channel_id}"

    def __repr__(self):
        return f"{self.message}"

    def __str__(self):
        return f"{self.message}"

    def __get_timestamp(self):
        if not isinstance(self.data, dict):
            return server_time(self.message) if isinstance(self.message, dict) else None
        if "timestamp" in self.data:
            return self.data["timestamp"]
        return server_time(self.data)

    def __get_channel_id(self):
        if not isinstance(self.data, dict):
            return self.topic_user
        if isinstance(self.data.get("prediction"), dict) and "channel_id" in self.data["prediction"]:
            return self.data["prediction"]["channel_id"]
        if isinstance(self.data.get("claim"), dict) and "channel_id" in self.data["claim"]:
            return self.data["claim"]["channel_id"]
        if "channel_id" in self.data:
            return self.data["channel_id"]
        if isinstance(self.data.get("balance"), dict) and "channel_id" in self.data["balance"]:
            return self.data["balance"]["channel_id"]
        return self.topic_user
