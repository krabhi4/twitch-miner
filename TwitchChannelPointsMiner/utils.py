import os
import re
import secrets
import socket
import string
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from os import path

import requests
from millify import millify

from TwitchChannelPointsMiner.constants import USER_AGENTS, GITHUB_url


def _millify(input, precision=2):
    return millify(input, precision)


def get_streamer_index(streamers: list, channel_id) -> int:
    try:
        return next(
            i for i, x in enumerate(streamers) if str(x.channel_id) == str(channel_id)
        )
    except StopIteration:
        return -1


def float_round(number, ndigits=2):
    return round(float(number), ndigits)


def server_time(message_data):
    return (
        datetime.fromtimestamp(message_data["server_time"], timezone.utc).isoformat()
        + "Z"
        if message_data is not None and "server_time" in message_data
        else datetime.fromtimestamp(time.time(), timezone.utc).isoformat() + "Z"
    )


def create_nonce(length=30) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_user_agent(browser: str) -> str:
    """try:
        return USER_AGENTS[platform.system()][browser]
    except KeyError:
        # return USER_AGENTS["Linux"]["FIREFOX"]
        # return USER_AGENTS["Windows"]["CHROME"]"""
    return USER_AGENTS["Android"]["TV"]
    # return USER_AGENTS["Android"]["App"]


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002500-\U00002587"
    "\U00002589-\U00002BEF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U00002587"
    "\U00002589-\U0001F251"
    "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff"
    "\u2640-\u2642"
    "\u2600-\u2B55"
    "\u200d"
    "\u23cf"
    "\u23e9"
    "\u231a"
    "\ufe0f"
    "\u3030"
    "\u231b"
    "\u2328"
    "\u23ea"
    "\u23eb"
    "\u23ec"
    "\u23ed"
    "\u23ee"
    "\u23ef"
    "\u23f0"
    "\u23f1"
    "\u23f2"
    "\u23f3"
    "]+",
    flags=re.UNICODE,
)


def remove_emoji(string: str) -> str:
    return EMOJI_PATTERN.sub(r"", string) if string else ""


def at_least_one_value_in_settings_is(items, attr, value=True):
    for item in items:
        if getattr(item.settings, attr) == value:
            return True
    return False


def copy_values_if_none(settings, defaults):
    values = list(
        filter(
            lambda x: x.startswith("__") is False
            and callable(getattr(settings, x)) is False,
            dir(settings),
        )
    )

    for value in values:
        if getattr(settings, value) is None:
            setattr(settings, value, getattr(defaults, value))
    return settings


def set_default_settings(settings, defaults):
    # If no settings was provided use the default settings ...
    # If settings was provided but maybe are only partial set
    # Get the default values from Settings.streamer_settings
    return (
        deepcopy(defaults)
        if settings is None
        else copy_values_if_none(settings, defaults)
    )


def internet_connection_available(host="8.8.8.8", port=53, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def percentage(a, b):
    return 0 if b == 0 else int((a / b) * 100)


def create_chunks(lst, n):
    return [lst[slice(i, i + n)] for i in range(0, len(lst), n)]


def download_file(name, fpath):
    try:
        url = f"{GITHUB_url.rstrip('/')}/{name.lstrip('/')}"
        r = requests.get(
            url,
            headers={"User-Agent": get_user_agent("FIREFOX")},
            stream=True,
            timeout=15,
        )
        if r.status_code == 200:
            dir_path = path.dirname(fpath)
            if dir_path:
                import os

                os.makedirs(dir_path, exist_ok=True)
            with open(fpath, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            return True
    except requests.RequestException:
        return False
    return False


def read(fname):
    with open(path.join(path.dirname(__file__), fname), encoding="utf-8") as f:
        return f.read()


def init2dict(content):
    return dict(re.findall(r"""__([a-z]+)__ = "([^"]+)""", content))


def check_versions():
    try:
        current_version = init2dict(read("__init__.py"))
        current_version = (
            current_version["version"] if "version" in current_version else "0.0.0"
        )
    except Exception:
        current_version = "0.0.0"
    try:
        r = requests.get(
            "/".join(
                [
                    s.strip("/")
                    for s in [GITHUB_url, "TwitchChannelPointsMiner", "__init__.py"]
                ]
            ),
            timeout=10,
        )
        github_version = init2dict(r.text)
        github_version = (
            github_version["version"] if "version" in github_version else "0.0.0"
        )
    except Exception:
        github_version = "0.0.0"
    return current_version, github_version


def is_docker() -> bool:
    return bool(
        os.path.exists("/.dockerenv")
        or os.environ.get("RUNNING_IN_DOCKER") == "1"
        or os.environ.get("DOCKER") == "1"
    )


def is_docker_run_py() -> bool:
    env_override = os.environ.get("DOCKER_RUN_PY")
    if env_override is not None:
        return env_override.lower() in ("1", "true", "yes")
    if not is_docker():
        return False
    if os.path.isfile("run.py") or os.path.isfile("/usr/src/app/run.py"):
        return True
    return any(os.path.basename(arg) == "run.py" for arg in sys.argv)


def apply_bet_settings_dict(blive, b: dict):
    if not blive or not b or not isinstance(b, dict):
        return
    from TwitchChannelPointsMiner.classes.entities.Bet import (
        Condition,
        DelayMode,
        FilterCondition,
        OutcomeKeys,
        Strategy,
    )

    for kb in [
        "percentage",
        "percentage_gap",
        "max_points",
        "minimum_points",
        "stealth_mode",
        "delay",
    ]:
        if kb in b and b[kb] is not None:
            setattr(blive, kb, b[kb])
    if "strategy" in b and b["strategy"]:
        try:
            blive.strategy = Strategy[b["strategy"]]
        except Exception:
            pass
    if "delay_mode" in b and b["delay_mode"]:
        try:
            blive.delay_mode = DelayMode[b["delay_mode"]]
        except Exception:
            pass
    if "filter_condition" in b:
        fc = b["filter_condition"]
        if fc is None:
            blive.filter_condition = None
        else:
            try:
                cond = FilterCondition(
                    by=(
                        OutcomeKeys[fc["by"]]
                        if fc.get("by") and hasattr(OutcomeKeys, fc["by"])
                        else fc.get("by")
                    ),
                    where=(
                        Condition[fc["where"]]
                        if fc.get("where") and hasattr(Condition, fc["where"])
                        else fc.get("where")
                    ),
                    value=fc.get("value"),
                )
                blive.filter_condition = cond
            except Exception:
                pass


def apply_streamer_settings_dict(settings, data: dict):
    if not settings or not data or not isinstance(data, dict):
        return
    from TwitchChannelPointsMiner.classes.Chat import ChatPresence
    from TwitchChannelPointsMiner.classes.entities.Bet import BetSettings

    for k in [
        "make_predictions",
        "follow_raid",
        "claim_drops",
        "claim_moments",
        "watch_streak",
        "community_goals",
    ]:
        if k in data and data[k] is not None:
            setattr(settings, k, data[k])

    if "chat" in data and data["chat"]:
        try:
            settings.chat = ChatPresence[data["chat"]]
        except Exception:
            pass

    if "bet" in data and data["bet"]:
        blive = getattr(settings, "bet", None)
        if blive is None:
            blive = BetSettings()
            settings.bet = blive
        apply_bet_settings_dict(blive, data["bet"])


def apply_settings_dict_to_streamer(streamer, data: dict):
    if (
        not streamer
        or not data
        or not hasattr(streamer, "settings")
        or not streamer.settings
    ):
        return
    apply_streamer_settings_dict(streamer.settings, data)


def parse_priority_list(items):
    if not items or not isinstance(items, list):
        return None
    from TwitchChannelPointsMiner.classes.Settings import Priority

    res = []
    for it in items:
        if isinstance(it, Priority):
            if it not in res:
                res.append(it)
            continue
        val = str(it).upper().replace("PRIORITY.", "").strip()
        p = getattr(Priority, val, None)
        if p and p not in res:
            res.append(p)
    return res if res else None
