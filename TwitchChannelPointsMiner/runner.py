import argparse
import logging
import os
import sys
from pathlib import Path

from TwitchChannelPointsMiner import TwitchChannelPointsMiner
from TwitchChannelPointsMiner.classes.AnalyticsServer import load_config_file
from TwitchChannelPointsMiner.classes.entities.Streamer import StreamerSettings
from TwitchChannelPointsMiner.classes.Settings import Priority
from TwitchChannelPointsMiner.logger import LoggerSettings
from TwitchChannelPointsMiner.utils import (
    apply_streamer_settings_dict,
    parse_priority_list,
)

logger = logging.getLogger(__name__)


def _detect_from_env() -> str:
    for key in ("TWITCH_USERNAME", "TWITCH_USER"):
        val = os.environ.get(key)
        if val and val.strip() and val.strip() != "your-twitch-username":
            return val.strip()
    user_env = os.environ.get("USERNAME")
    if (
        user_env
        and user_env.strip()
        and user_env.strip() not in ("root", "your-twitch-username")
    ):
        return user_env.strip()
    return None


def _detect_from_cookies() -> str:
    cookies_dir = Path("cookies")
    if not cookies_dir.is_dir():
        return None
    for p in sorted(cookies_dir.glob("*.pkl")):
        stem = p.stem.strip()
        if (
            stem
            and not stem.upper().startswith("CHANGE_ME")
            and stem != "your-twitch-username"
        ):
            return stem
    return None


def _detect_from_analytics() -> str:
    analytics_dir = Path("analytics")
    if not analytics_dir.is_dir():
        return None
    for p in sorted(analytics_dir.iterdir()):
        if not p.is_dir():
            continue
        name = p.name.strip()
        if (
            name
            and not name.upper().startswith("CHANGE_ME")
            and not name.startswith(".")
            and name != "__pycache__"
            and name != "your-twitch-username"
        ):
            return name
    return None


def detect_username(explicit: str = None) -> str:
    if explicit and explicit.strip() and explicit.strip() != "your-twitch-username":
        return explicit.strip()
    return _detect_from_env() or _detect_from_cookies() or _detect_from_analytics()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--username", dest="username", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("-p", "--port", type=int, default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("streamers", nargs="*", default=[])

    args, unknown = parser.parse_known_args()

    explicit_user = args.username
    streamers = list(args.streamers)

    if not explicit_user and streamers:
        discovered = detect_username(None)
        if not discovered:
            explicit_user = streamers.pop(0)

    target_user = detect_username(explicit_user)
    if not target_user:
        logger.error(
            "No Twitch username found. Please set TWITCH_USERNAME "
            "or mount cookies/<username>.pkl."
        )
        sys.exit(1)

    password = (
        args.password or os.environ.get("TWITCH_PASSWORD") or os.environ.get("PASSWORD")
    )

    host = args.host or os.environ.get("HOST", "0.0.0.0")
    port = args.port if args.port is not None else int(os.environ.get("PORT", "5000"))
    refresh = int(os.environ.get("REFRESH", "5"))
    days_ago = int(os.environ.get("DAYS_AGO", "7"))

    cfg = load_config_file(target_user)
    streamer_settings = StreamerSettings()
    priority = [Priority.STREAK, Priority.DROPS, Priority.ORDER]

    if cfg:
        if isinstance(cfg.get("global"), dict):
            apply_streamer_settings_dict(streamer_settings, cfg["global"])
        if isinstance(cfg.get("priority"), list):
            parsed_p = parse_priority_list(cfg["priority"])
            if parsed_p:
                priority = parsed_p

    twitch_miner = TwitchChannelPointsMiner(
        username=target_user,
        password=password,
        priority=priority,
        enable_analytics=True,
        streamer_settings=streamer_settings,
        logger_settings=LoggerSettings(save=True, auto_clear=True),
    )

    twitch_miner.analytics(
        host=host,
        port=port,
        refresh=refresh,
        days_ago=days_ago,
    )

    twitch_miner.mine(streamers, followers=False)


if __name__ == "__main__":
    run()
