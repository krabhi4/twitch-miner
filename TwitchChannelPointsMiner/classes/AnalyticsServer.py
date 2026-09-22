import copy
import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from threading import Thread

import pandas as pd
from flask import Flask, Response, cli, render_template, request, send_from_directory

from TwitchChannelPointsMiner.classes.Exceptions import StreamerDoesNotExistException
from TwitchChannelPointsMiner.classes.Settings import Settings
from TwitchChannelPointsMiner.utils import (
    apply_settings_dict_to_streamer,
    download_file,
    is_docker_run_py,
)

cli.show_server_banner = lambda *_: None
logger = logging.getLogger(__name__)


def streamers_available():
    from TwitchChannelPointsMiner.classes.Database import get_database

    db = get_database()
    username = (
        getattr(Settings, "analytics_username", None)
        or os.path.basename(getattr(Settings, "analytics_path", "") or "")
        or db.get_any_username()
    )
    if not username:
        return []
    return [f"{s}.json" for s in db.get_streamers(username)]


def aggregate(df, freq="30Min"):
    df_base_events = df[(df.z == "Watch") | (df.z == "Claim")]
    df_other_events = df[(df.z != "Watch") & (df.z != "Claim")]

    be = df_base_events.groupby([pd.Grouper(freq=freq, key="datetime"), "z"]).max()
    be = be.reset_index()

    oe = df_other_events.groupby([pd.Grouper(freq=freq, key="datetime"), "z"]).max()
    oe = oe.reset_index()

    result = pd.concat([be, oe])
    return result


def read_json(streamer, return_response=True):
    start_date = request.args.get("startDate", type=str) if request else None
    end_date = request.args.get("endDate", type=str) if request else None

    from TwitchChannelPointsMiner.classes.Database import get_database

    db = get_database()
    username = (
        getattr(Settings, "analytics_username", None)
        or os.path.basename(getattr(Settings, "analytics_path", "") or "")
        or db.get_any_username()
    )

    streamer_clean = os.path.basename(streamer).replace(".json", "").lower().strip()

    start_ts = None
    if start_date:
        try:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        except Exception:
            start_ts = None

    end_ts = None
    if end_date:
        try:
            end_ts = int(
                datetime.strptime(end_date, "%Y-%m-%d")
                .replace(hour=23, minute=59, second=59)
                .timestamp()
                * 1000
            )
        except Exception:
            end_ts = None

    data = db.get_streamer_data(
        username, streamer_clean, start_date=start_ts, end_date=end_ts
    )

    if start_ts is not None and len(data.get("series", [])) == 0:
        baseline = db.get_streamer_data(username, streamer_clean, end_date=start_ts)
        if baseline.get("series"):
            last_y = baseline["series"][-1]["y"]
            end_bound = end_ts if end_ts is not None else int(time.time() * 1000)
            data["series"] = [
                {"x": start_ts, "y": last_y, "z": "No Stream"},
                {"x": end_bound, "y": last_y, "z": "No Stream"},
            ]

    if return_response:
        return Response(json.dumps(data), status=200, mimetype="application/json")
    return data


def get_challenge_points(streamer):
    streamer_clean = os.path.basename(streamer).replace(".json", "").lower().strip()
    from TwitchChannelPointsMiner.classes.Database import get_database

    db = get_database()
    username = (
        getattr(Settings, "analytics_username", None)
        or os.path.basename(getattr(Settings, "analytics_path", "") or "")
        or db.get_any_username()
    )
    pt = db.get_last_series_point(username, streamer_clean)
    return pt.get("y", 0)


def get_last_activity(streamer):
    streamer_clean = os.path.basename(streamer).replace(".json", "").lower().strip()
    from TwitchChannelPointsMiner.classes.Database import get_database

    db = get_database()
    username = (
        getattr(Settings, "analytics_username", None)
        or os.path.basename(getattr(Settings, "analytics_path", "") or "")
        or db.get_any_username()
    )
    pt = db.get_last_series_point(username, streamer_clean)
    return pt.get("x", 0)


def json_all():
    return Response(
        json.dumps(
            [
                {
                    "name": streamer.removesuffix(".json"),
                    "data": read_json(streamer, return_response=False),
                }
                for streamer in streamers_available()
            ]
        ),
        status=200,
        mimetype="application/json",
    )


def index(refresh=5, days_ago=7):
    return render_template(
        "charts.html",
        refresh=(refresh * 60 * 1000),
        daysAgo=days_ago,
        can_add_streamer=not is_docker_run_py(),
    )


def streamers():
    return Response(
        json.dumps(
            [
                {
                    "name": s,
                    "points": get_challenge_points(s),
                    "last_activity": get_last_activity(s),
                }
                for s in sorted(streamers_available())
            ]
        ),
        status=200,
        mimetype="application/json",
    )


def get_config_path(username):
    base = getattr(Settings, "analytics_path", None)
    if base:
        return os.path.join(base, "config.json")
    if username:
        return os.path.join(Path().absolute(), "analytics", username, "config.json")
    return os.path.join(Path().absolute(), "analytics", "config.json")


def serialize_bet(bet):
    if bet is None:
        return None
    fc = None
    if getattr(bet, "filter_condition", None) is not None:
        fc = bet.filter_condition
        fc_dict = {
            "by": str(fc.by) if fc.by else None,
            "where": str(fc.where) if fc.where else None,
            "value": fc.value,
        }
    else:
        fc_dict = None
    return {
        "strategy": str(bet.strategy) if bet.strategy else None,
        "percentage": bet.percentage,
        "percentage_gap": bet.percentage_gap,
        "max_points": bet.max_points,
        "minimum_points": bet.minimum_points,
        "stealth_mode": bet.stealth_mode,
        "delay": bet.delay,
        "delay_mode": str(bet.delay_mode) if bet.delay_mode else None,
        "filter_condition": fc_dict,
    }


def serialize_streamer_settings(s):
    if s is None:
        return None
    return {
        "make_predictions": s.make_predictions,
        "follow_raid": s.follow_raid,
        "claim_drops": s.claim_drops,
        "claim_moments": s.claim_moments,
        "watch_streak": s.watch_streak,
        "community_goals": s.community_goals,
        "chat": str(s.chat) if s.chat else None,
        "bet": serialize_bet(getattr(s, "bet", None)),
    }


def load_config_file(username):
    from TwitchChannelPointsMiner.classes.Database import get_database

    db = get_database(username=username)
    cfg = db.load_config(username)
    if cfg is not None:
        return cfg
    path = get_config_path(username)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            db.save_config(username, cfg)
            Path(path).unlink(missing_ok=True)
            return cfg
        except Exception as e:
            logger.error(f"Failed to load config {path}: {e}")
    return None


def save_config_file(username, data):
    from TwitchChannelPointsMiner.classes.Database import get_database

    db = get_database(username=username)
    db.save_config(username, data)
    path = get_config_path(username)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except Exception:
            pass
    return path


def default_global_config():
    try:
        gs = getattr(Settings, "streamer_settings", None)
        if gs is not None and hasattr(gs, "make_predictions"):
            return serialize_streamer_settings(gs)
    except Exception:
        pass
    return {
        "make_predictions": False,
        "follow_raid": True,
        "claim_drops": True,
        "claim_moments": True,
        "watch_streak": True,
        "community_goals": False,
        "chat": "ONLINE",
        "bet": {
            "strategy": "SMART",
            "percentage": 5,
            "percentage_gap": 20,
            "max_points": 50000,
            "minimum_points": 0,
            "stealth_mode": False,
            "delay": 6,
            "delay_mode": "FROM_END",
            "filter_condition": None,
        },
    }


def compute_streamer_stats(streamer_file, username=None):
    from TwitchChannelPointsMiner.classes.Database import get_database

    db = get_database(username=username)
    username = (
        username
        or getattr(Settings, "analytics_username", None)
        or os.path.basename(getattr(Settings, "analytics_path", "") or "")
        or db.get_any_username()
    )
    clean_name = os.path.basename(streamer_file).replace(".json", "").strip()
    name = clean_name.lower()
    data = db.get_streamer_data(username, name)

    series = data.get("series", [])
    annotations = data.get("annotations", [])

    if not series:
        return {
            "name": clean_name,
            "file": os.path.basename(streamer_file),
            "points": 0,
            "last_activity": 0,
            "total_gained": 0,
            "series_count": 0,
            "bets": {"placed": 0, "wins": 0, "losses": 0, "win_rate": 0},
        }

    points = series[-1].get("y", 0)
    last_activity = series[-1].get("x", 0)
    first_y = series[0].get("y", points)
    total_gained = points - first_y

    z_counter = Counter([s.get("z", "Unknown") for s in series])
    gains_by_reason = defaultdict(int)
    for i in range(1, len(series)):
        delta = series[i].get("y", 0) - series[i - 1].get("y", 0)
        if delta > 0:
            reason = series[i].get("z", "Unknown")
            gains_by_reason[reason] += delta

    color_map = {"#45c1ff": 0, "#ffe045": 0, "#36b535": 0, "#ff4545": 0}
    for a in annotations:
        c = a.get("borderColor")
        if c in color_map:
            color_map[c] += 1

    placed = color_map["#ffe045"]
    wins = color_map["#36b535"]
    losses = color_map["#ff4545"]
    streaks = color_map["#45c1ff"]
    win_rate = round((wins / (wins + losses) * 100) if (wins + losses) > 0 else 0, 1)

    history = {
        k: {"counter": z_counter.get(k, 0), "amount": gains_by_reason.get(k, 0)}
        for k in set(list(z_counter.keys()) + list(gains_by_reason.keys()))
    }

    return {
        "name": clean_name,
        "file": os.path.basename(streamer_file),
        "points": points,
        "last_activity": last_activity,
        "first_y": first_y,
        "total_gained": total_gained,
        "series_count": len(series),
        "annotations_count": len(annotations),
        "z_counter": dict(z_counter),
        "gains_by_reason": dict(gains_by_reason),
        "history": history,
        "bets": {
            "placed": placed,
            "wins": wins,
            "losses": losses,
            "streaks": streaks,
            "win_rate": win_rate,
        },
    }


def api_overview(username):
    files = streamers_available()
    stats_list = [compute_streamer_stats(f, username) for f in files]
    total_points = sum(s.get("points", 0) for s in stats_list)
    total_gained = sum(s.get("total_gained", 0) for s in stats_list)
    total_bets = sum(s.get("bets", {}).get("placed", 0) for s in stats_list)
    total_wins = sum(s.get("bets", {}).get("wins", 0) for s in stats_list)
    total_losses = sum(s.get("bets", {}).get("losses", 0) for s in stats_list)
    top = max(stats_list, key=lambda x: x.get("points", 0)) if stats_list else None
    return {
        "total_streamers": len(files),
        "total_points": total_points,
        "total_gained": total_gained,
        "total_bets": total_bets,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "win_rate": round(
            (
                (total_wins / (total_wins + total_losses) * 100)
                if (total_wins + total_losses) > 0
                else 0
            ),
            1,
        ),
        "top_streamer": top.get("name") if top else None,
        "streamers": stats_list,
    }


def api_bet_history(username, streamer=None):
    from TwitchChannelPointsMiner.classes.Database import get_database

    db = get_database(username=username)
    user = (
        username or getattr(Settings, "miner_username", None) or db.get_any_username()
    )
    if streamer:
        streamers = [streamer.lower().strip().replace(".json", "")]
    else:
        streamers = [s.replace(".json", "") for s in streamers_available()]
    rows = []
    for name in streamers:
        data = db.get_streamer_data(user, name)
        annotations = data.get("annotations", [])
        series = data.get("series", [])
        for ann in annotations:
            color = ann.get("borderColor")
            text = ann.get("label", {}).get("text", "")
            x = ann.get("x", 0)
            if color == "#ffe045":
                typ = "BET_PLACED"
            elif color == "#36b535":
                typ = "WIN"
            elif color == "#ff4545":
                typ = "LOSE"
            elif color == "#45c1ff":
                typ = "WATCH_STREAK"
            else:
                typ = "OTHER"
            balance = None
            for s in reversed(series):
                if s["x"] <= x:
                    balance = s["y"]
                    break
            rows.append(
                {
                    "streamer": name,
                    "type": typ,
                    "color": color,
                    "text": text,
                    "x": x,
                    "datetime": (
                        datetime.fromtimestamp(x / 1000).isoformat() if x else None
                    ),
                    "balance": balance,
                }
            )
    rows.sort(key=lambda r: r["x"], reverse=True)
    return rows


def api_enums():
    return {
        "strategies": [
            "MOST_VOTED",
            "HIGH_ODDS",
            "PERCENTAGE",
            "SMART_MONEY",
            "SMART",
            "NUMBER_1",
            "NUMBER_2",
            "NUMBER_3",
            "NUMBER_4",
            "NUMBER_5",
            "NUMBER_6",
            "NUMBER_7",
            "NUMBER_8",
        ],
        "delay_modes": ["FROM_START", "FROM_END", "PERCENTAGE"],
        "chat_presences": ["ALWAYS", "NEVER", "ONLINE", "OFFLINE"],
        "outcome_keys": [
            "PERCENTAGE_USERS",
            "ODDS_PERCENTAGE",
            "ODDS",
            "TOP_POINTS",
            "TOTAL_USERS",
            "TOTAL_POINTS",
            "DECISION_USERS",
            "DECISION_POINTS",
        ],
        "conditions": ["GT", "LT", "GTE", "LTE"],
        "priorities": [
            "STREAK",
            "DROPS",
            "ORDER",
            "SUBSCRIBED",
            "POINTS_ASCENDING",
            "POINTS_DESCENDING",
        ],
    }


def download_assets(assets_folder, required_files):
    Path(assets_folder).mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading assets to {assets_folder}")

    for f in required_files:
        if os.path.isfile(os.path.join(assets_folder, f)) is False:
            if (
                download_file(os.path.join("assets", f), os.path.join(assets_folder, f))
                is True
            ):
                logger.info(f"Downloaded {f}")


def check_assets():
    required_files = [
        "charts.html",
        "logs.html",
        "script.js",
        "style.css",
        "dark-theme.css",
    ]
    assets_folder = os.path.join(Path().absolute(), "assets")
    if os.path.isdir(assets_folder) is False:
        logger.info(f"Assets folder not found at {assets_folder}")
        download_assets(assets_folder, required_files)
    else:
        for f in required_files:
            if os.path.isfile(os.path.join(assets_folder, f)) is False:
                logger.info(f"Missing file {f} in {assets_folder}")
                download_assets(assets_folder, required_files)
                break


class AnalyticsServer(Thread):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        refresh: int = 5,
        days_ago: int = 7,
        username: str = None,
        miner=None,
    ):
        super(AnalyticsServer, self).__init__()

        check_assets()

        self.host = host
        self.port = port
        self.refresh = refresh
        self.days_ago = days_ago
        self.username = username
        self.miner = miner

        def generate_log():
            try:
                last_received_index = int(request.args.get("lastIndex", 0))
            except (ValueError, TypeError):
                last_received_index = 0
            logs_path = os.path.join(Path().absolute(), "logs")
            log_file_path = os.path.join(logs_path, f"{username}.log")
            if not os.path.isfile(log_file_path):
                return Response(
                    "Log file not found.", status=404, mimetype="text/plain"
                )
            if request.args.get("raw") == "true":
                try:
                    return send_from_directory(
                        logs_path, f"{username}.log", mimetype="text/plain"
                    )
                except Exception as e:
                    logger.error(f"Error serving raw log: {e}")
            try:
                file_size = os.path.getsize(log_file_path)
                with open(
                    log_file_path, "r", encoding="utf-8", errors="replace"
                ) as log_file:
                    if last_received_index <= 0 or last_received_index > file_size:
                        start_pos = max(0, file_size - 64 * 1024)
                        log_file.seek(start_pos)
                        if start_pos > 0:
                            log_file.readline()
                    else:
                        log_file.seek(last_received_index)
                    new_log_entries = log_file.read(256 * 1024)
                    new_offset = log_file.tell()
                resp = Response(new_log_entries, status=200, mimetype="text/plain")
                resp.headers["X-Log-Offset"] = str(new_offset)
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                return resp
            except Exception as e:
                logger.error(f"Error reading log file {log_file_path}: {e}")
                return Response(
                    "Error reading log file.", status=500, mimetype="text/plain"
                )

        def logs_view():
            if request.args.get("raw") == "true" or (
                "text/plain" in request.headers.get("Accept", "")
                and "text/html" not in request.headers.get("Accept", "")
            ):
                return generate_log()
            return render_template("logs.html")

        def api_config_get():
            can_add = not is_docker_run_py()
            saved = load_config_file(username)
            if saved:
                resp_data = dict(saved)
                resp_data["can_add_streamer"] = can_add
                if "streamers" not in resp_data or not isinstance(
                    resp_data["streamers"], dict
                ):
                    resp_data["streamers"] = {}
                existing_lower = {k.lower() for k in resp_data["streamers"]}
                if self.miner and hasattr(self.miner, "streamers"):
                    for s in self.miner.streamers:
                        if s.username.lower() not in existing_lower:
                            resp_data["streamers"][s.username] = (
                                serialize_streamer_settings(s.settings)
                                if hasattr(s, "settings") and s.settings
                                else None
                            )
                return Response(
                    json.dumps(resp_data),
                    status=200,
                    mimetype="application/json",
                )
            live_global = default_global_config()
            streamers_cfg = {}
            if self.miner and hasattr(self.miner, "streamers"):
                for s in self.miner.streamers:
                    if hasattr(s, "settings") and s.settings:
                        streamers_cfg[s.username] = serialize_streamer_settings(
                            s.settings
                        )
                    else:
                        streamers_cfg[s.username] = None
            out = {
                "global": live_global,
                "streamers": streamers_cfg,
                "priority": (
                    [str(p) for p in getattr(self.miner, "priority", [])]
                    if self.miner and hasattr(self.miner, "priority")
                    else []
                ),
                "can_add_streamer": can_add,
            }
            return Response(json.dumps(out), status=200, mimetype="application/json")

        def api_config_put():
            try:
                data = request.get_json(force=True)
            except Exception as e:
                return Response(
                    json.dumps({"error": str(e)}),
                    status=400,
                    mimetype="application/json",
                )
            existing = load_config_file(username) or {
                "global": default_global_config(),
                "streamers": {},
                "priority": [],
            }
            if "global" in data:
                existing["global"] = data["global"]
                try:
                    from TwitchChannelPointsMiner.classes.Chat import ChatPresence
                    from TwitchChannelPointsMiner.classes.entities.Bet import (
                        Condition,
                        DelayMode,
                        FilterCondition,
                        OutcomeKeys,
                        Strategy,
                    )

                    gs = existing["global"]
                    try:
                        _live_tmp = getattr(Settings, "streamer_settings", None)
                        live = (
                            _live_tmp
                            if _live_tmp is not None
                            and hasattr(_live_tmp, "make_predictions")
                            else None
                        )
                    except Exception:
                        live = None
                    if live:
                        for k in [
                            "make_predictions",
                            "follow_raid",
                            "claim_drops",
                            "claim_moments",
                            "watch_streak",
                            "community_goals",
                        ]:
                            if k in gs:
                                setattr(live, k, gs[k])
                        if "chat" in gs and gs["chat"]:
                            try:
                                setattr(live, "chat", ChatPresence[gs["chat"]])
                            except Exception:
                                pass
                        if "bet" in gs and gs["bet"]:
                            b = gs["bet"]
                            blive = live.bet
                            for kb in [
                                "percentage",
                                "percentage_gap",
                                "max_points",
                                "minimum_points",
                                "stealth_mode",
                                "delay",
                            ]:
                                if kb in b:
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
                                        blive.filter_condition = FilterCondition(
                                            by=(
                                                OutcomeKeys[fc["by"]]
                                                if fc.get("by")
                                                else None
                                            ),
                                            where=(
                                                Condition[fc["where"]]
                                                if fc.get("where")
                                                else None
                                            ),
                                            value=fc.get("value"),
                                        )
                                    except Exception:
                                        pass
                except Exception as e:
                    logger.error(f"Failed to apply live config: {e}")
            if "streamers" in data:
                existing["streamers"] = data["streamers"]
            if "priority" in data:
                existing["priority"] = data["priority"]
            save_config_file(username, existing)
            return Response(
                json.dumps({"status": "ok", "config": existing}),
                status=200,
                mimetype="application/json",
            )

        def api_streamer_put(name):
            try:
                data = request.get_json(force=True)
            except Exception as e:
                return Response(
                    json.dumps({"error": str(e)}),
                    status=400,
                    mimetype="application/json",
                )
            name_clean = name.strip()
            name_lower = name_clean.lower()
            cfg = load_config_file(username) or {
                "global": default_global_config(),
                "streamers": {},
                "priority": [],
            }
            streamers = cfg.setdefault("streamers", {})
            target_key = next(
                (k for k in streamers if k.lower() == name_lower),
                name_clean,
            )
            streamers[target_key] = data
            if self.miner and hasattr(self.miner, "streamers"):
                for s in self.miner.streamers:
                    if s.username.lower() == name_lower:
                        try:
                            apply_settings_dict_to_streamer(s, data)
                        except Exception as e:
                            logger.error(f"live update failed for {name_clean}: {e}")
            save_config_file(username, cfg)
            return Response(
                json.dumps({"status": "ok", "streamer": target_key, "settings": data}),
                status=200,
                mimetype="application/json",
            )

        def api_streamer_delete(name):
            name = name.lower().strip()
            cfg = load_config_file(username) or {
                "global": default_global_config(),
                "streamers": {},
                "priority": [],
            }
            streamers = cfg.setdefault("streamers", {})
            key = next((k for k in streamers if k.lower() == name), None)
            deleted = bool(streamers.pop(key, None)) if key else False
            if not is_docker_run_py():
                if self.miner and hasattr(self.miner, "remove_streamer"):
                    try:
                        if self.miner.remove_streamer(name):
                            deleted = True
                    except Exception as e:
                        logger.error(
                            f"Failed to remove streamer {name} from miner: {e}"
                        )
            else:
                if self.miner and hasattr(self.miner, "streamers"):
                    target = next(
                        (s for s in self.miner.streamers if s.username.lower() == name),
                        None,
                    )
                    if target:
                        if (
                            hasattr(Settings, "streamer_settings")
                            and Settings.streamer_settings
                        ):
                            target.settings = copy.deepcopy(Settings.streamer_settings)
                        deleted = True
            if deleted:
                save_config_file(username, cfg)
                from TwitchChannelPointsMiner.classes.Database import get_database

                get_database(username=username).delete_streamer(username, name)
                return Response(
                    json.dumps({"status": "deleted", "streamer": name}),
                    status=200,
                    mimetype="application/json",
                )
            return Response(
                json.dumps({"error": "not found"}),
                status=404,
                mimetype="application/json",
            )

        def api_streamer_add():
            if is_docker_run_py():
                return Response(
                    json.dumps(
                        {
                            "error": (
                                "Adding streamers via settings is disabled "
                                "when run.py is configured via Docker"
                            )
                        }
                    ),
                    status=403,
                    mimetype="application/json",
                )
            try:
                data = request.get_json(force=True)
            except Exception as e:
                return Response(
                    json.dumps({"error": str(e)}),
                    status=400,
                    mimetype="application/json",
                )
            name = data.get("username") or data.get("name")
            if not name:
                return Response(
                    json.dumps({"error": "username required"}),
                    status=400,
                    mimetype="application/json",
                )
            name = name.lower().strip()
            if not re.match(r"^[a-zA-Z0-9_]{3,25}$", name):
                return Response(
                    json.dumps({"error": "Invalid Twitch username format"}),
                    status=400,
                    mimetype="application/json",
                )
            settings = data.get("settings")
            cfg = load_config_file(username) or {
                "global": default_global_config(),
                "streamers": {},
                "priority": [],
            }
            streamers = cfg.setdefault("streamers", {})
            if not isinstance(streamers, dict):
                cfg["streamers"] = streamers = {}
            existing_lower = {k.lower() for k in streamers}
            is_in_cfg = name in existing_lower
            is_in_miner = bool(
                self.miner
                and any(
                    s.username.lower() == name
                    for s in getattr(self.miner, "streamers", [])
                )
            )
            if is_in_cfg or is_in_miner:
                return Response(
                    json.dumps({"error": f"Streamer '{name}' already exists"}),
                    status=409,
                    mimetype="application/json",
                )

            new_streamer = None
            if self.miner and hasattr(self.miner, "add_streamer"):
                try:
                    new_streamer = self.miner.add_streamer(name)
                except StreamerDoesNotExistException:
                    return Response(
                        json.dumps(
                            {"error": (f"Streamer '{name}' does not exist on Twitch")}
                        ),
                        status=404,
                        mimetype="application/json",
                    )
                except Exception as e:
                    logger.error(f"Failed to add streamer {name} to miner: {e}")
                    return Response(
                        json.dumps({"error": f"Failed to add streamer: {str(e)}"}),
                        status=500,
                        mimetype="application/json",
                    )

            if new_streamer and settings and isinstance(settings, dict):
                try:
                    apply_settings_dict_to_streamer(new_streamer, settings)
                except Exception as e:
                    logger.error(f"Failed to apply initial settings to {name}: {e}")

            cfg["streamers"][name] = settings if settings is not None else None
            save_config_file(username, cfg)
            return Response(
                json.dumps({"status": "created", "streamer": name}),
                status=201,
                mimetype="application/json",
            )

        def api_overview_handler():
            data = api_overview(username)
            return Response(json.dumps(data), status=200, mimetype="application/json")

        def api_bets_handler():
            streamer = request.args.get("streamer", type=str)
            limit = request.args.get("limit", type=int) or 100
            type_filter = request.args.get("type", type=str)
            rows = api_bet_history(username, streamer)
            if type_filter:
                rows = [r for r in rows if r["type"] == type_filter.upper()]
            rows = rows[:limit]
            return Response(json.dumps(rows), status=200, mimetype="application/json")

        def api_streamers_details():
            files = streamers_available()
            out = []
            cfg = load_config_file(username) or {}
            streamers_cfg = cfg.get("streamers") if isinstance(cfg, dict) else {}
            if not isinstance(streamers_cfg, dict):
                streamers_cfg = {}
            miner_streamers = (
                getattr(self.miner, "streamers", [])
                if self.miner and hasattr(self.miner, "streamers")
                else []
            )
            for f in files:
                stats = compute_streamer_stats(f, username)
                if not isinstance(stats, dict):
                    continue
                s_name = stats.get("name") or os.path.basename(f).replace(".json", "").strip()
                stats["name"] = s_name
                if "file" not in stats:
                    stats["file"] = os.path.basename(f)
                per_stream_cfg = streamers_cfg.get(s_name) or streamers_cfg.get(s_name.lower())
                stats["config"] = per_stream_cfg
                for s in miner_streamers:
                    if getattr(s, "username", "").lower() == s_name.lower():
                        stats["is_online"] = getattr(s, "is_online", False)
                        stats["channel_points_live"] = getattr(s, "channel_points", 0)
                        break
                out.append(stats)
            out.sort(key=lambda x: x.get("points", 0), reverse=True)
            return Response(json.dumps(out), status=200, mimetype="application/json")

        def api_enums_handler():
            return Response(
                json.dumps(api_enums()), status=200, mimetype="application/json"
            )

        def api_series_aggregate(streamer):
            freq = request.args.get("freq", type=str) or "30Min"
            data = read_json(streamer, return_response=False)
            if "error" in data:
                return Response(
                    json.dumps(data), status=404, mimetype="application/json"
                )
            if freq != "raw" and "series" in data and data["series"]:
                try:
                    df = pd.DataFrame(data["series"])
                    df["datetime"] = pd.to_datetime(df.x // 1000, unit="s")
                    agg = aggregate(df, freq=freq)
                    data["series"] = (
                        agg.drop(columns="datetime")
                        .sort_values(by=["x", "y"])
                        .to_dict("records")
                        if "x" in agg
                        else data["series"]
                    )
                except Exception as e:
                    logger.error(f"aggregate failed: {e}")
            return Response(json.dumps(data), status=200, mimetype="application/json")

        self.app = Flask(
            __name__,
            template_folder=os.path.join(Path().absolute(), "assets"),
            static_folder=os.path.join(Path().absolute(), "assets"),
        )
        self.app.config["TEMPLATES_AUTO_RELOAD"] = True
        self.app.add_url_rule(
            "/",
            "index",
            index,
            defaults={"refresh": refresh, "days_ago": days_ago},
            methods=["GET"],
        )
        self.app.add_url_rule("/streamers", "streamers", streamers, methods=["GET"])
        self.app.add_url_rule(
            "/json/<string:streamer>", "json", read_json, methods=["GET"]
        )
        self.app.add_url_rule("/json_all", "json_all", json_all, methods=["GET"])
        self.app.add_url_rule("/log", "log", generate_log, methods=["GET"])
        self.app.add_url_rule("/logs", "logs", logs_view, methods=["GET"])
        self.app.add_url_rule(
            "/api/config", "api_config_get", api_config_get, methods=["GET"]
        )
        self.app.add_url_rule(
            "/api/config", "api_config_put", api_config_put, methods=["PUT"]
        )
        self.app.add_url_rule(
            "/api/config/streamer/<string:name>",
            "api_streamer_put",
            api_streamer_put,
            methods=["PUT"],
        )
        self.app.add_url_rule(
            "/api/config/streamer/<string:name>",
            "api_streamer_delete",
            api_streamer_delete,
            methods=["DELETE"],
        )
        self.app.add_url_rule(
            "/api/config/streamer",
            "api_streamer_add",
            api_streamer_add,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/overview", "api_overview", api_overview_handler, methods=["GET"]
        )
        self.app.add_url_rule(
            "/api/bets", "api_bets", api_bets_handler, methods=["GET"]
        )
        self.app.add_url_rule(
            "/api/streamers/details",
            "api_streamers_details",
            api_streamers_details,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/enums", "api_enums", api_enums_handler, methods=["GET"]
        )
        self.app.add_url_rule(
            "/api/series/<string:streamer>",
            "api_series_agg",
            api_series_aggregate,
            methods=["GET"],
        )

    def run(self):
        logger.info(
            f"Analytics running on http://{self.host}:{self.port}/",
            extra={"emoji": ":globe_with_meridians:"},
        )
        self.app.run(host=self.host, port=self.port, threaded=True, debug=False)
