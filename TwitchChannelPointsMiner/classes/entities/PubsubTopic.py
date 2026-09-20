class PubsubTopic(object):
    __slots__ = ["topic", "user_id", "streamer"]

    def __init__(self, topic, user_id=None, streamer=None):
        self.topic = topic
        self.user_id = user_id
        self.streamer = streamer

    def is_user_topic(self):
        return self.streamer is None

    def __str__(self):
        if self.is_user_topic():
            return f"{self.topic}.{self.user_id}"
        else:
            channel_id = getattr(self.streamer, "channel_id", self.streamer)
            return f"{self.topic}.{channel_id}"

    def __repr__(self):
        return f"PubsubTopic(topic={self.topic}, user_id={self.user_id}, streamer={self.streamer})"

    def __eq__(self, other):
        if isinstance(other, PubsubTopic):
            return str(self) == str(other)
        return False

    def __hash__(self):
        return hash(str(self))
