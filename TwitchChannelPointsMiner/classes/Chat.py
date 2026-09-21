import functools
import logging
import ssl
import time
from enum import Enum, auto
from threading import Thread

from irc.bot import SingleServerIRCBot
from irc.connection import Factory

from TwitchChannelPointsMiner.constants import IRC, IRC_PORT
from TwitchChannelPointsMiner.classes.Settings import Events, Settings

logger = logging.getLogger(__name__)


class ChatPresence(Enum):
    ALWAYS = auto()
    NEVER = auto()
    ONLINE = auto()
    OFFLINE = auto()

    def __str__(self):
        return self.name


class ClientIRC(SingleServerIRCBot):
    def __init__(self, username, token, channel):
        self.token = token
        self.channel = f"#{channel.lstrip('#')}"
        self.__active = False
        ssl_context = ssl.create_default_context()
        ssl_factory = Factory(
            wrapper=functools.partial(ssl_context.wrap_socket, server_hostname=IRC)
        )

        password = token if token.startswith("oauth:") else f"oauth:{token}"
        super(ClientIRC, self).__init__(
            [(IRC, IRC_PORT, password)],
            username,
            username,
            connect_factory=ssl_factory,
        )

    def on_welcome(self, client, event):
        client.join(self.channel)

    def start(self):
        self.__active = True
        self._connect()
        while self.__active:
            try:
                self.reactor.process_once(timeout=0.2)
                time.sleep(0.01)
            except Exception as e:
                if not self.__active:
                    break
                logger.error(
                    f"Exception raised: {e}. Thread is active: {self.__active}"
                )

    def die(self, msg="Bye, cruel world!"):
        self.__active = False
        if self.connection is not None:
            self.connection.disconnect(msg)

    def on_pubmsg(self, connection, event):
        if not event.arguments:
            return
        msg = event.arguments[0]
        mention = None

        nickname = getattr(self, "_nickname", None) or getattr(self, "nickname", None) or getattr(self, "_realname", None) or ""
        if not nickname:
            return
        if Settings.disable_at_in_nickname:
            mention = f"{nickname.lower()}"
        else:
            mention = f"@{nickname.lower()}"

        if mention is not None and mention in msg.lower():
            nick = event.source.split("!", 1)[0]
            logger.info(f"{nick} at {self.channel} wrote: {msg}", extra={
                        "emoji": ":speech_balloon:", "event": Events.CHAT_MENTION})


class ThreadChat(Thread):
    def __deepcopy__(self, memo):
        return None

    def __init__(self, username, token, channel):
        super(ThreadChat, self).__init__(daemon=True)

        self.username = username
        self.token = token
        self.channel = channel

        self.chat_irc = None

    def run(self):
        self.chat_irc = ClientIRC(self.username, self.token, self.channel)
        logger.info(
            f"Join IRC Chat: {self.channel}", extra={"emoji": ":speech_balloon:"}
        )
        self.chat_irc.start()

    def stop(self):
        if self.chat_irc is not None:
            logger.info(
                f"Leave IRC Chat: {self.channel}", extra={"emoji": ":speech_balloon:"}
            )
            self.chat_irc.die()
