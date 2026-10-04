from datetime import datetime, timezone

from TwitchChannelPointsMiner.classes.entities.Drop import Drop, parse_datetime
from TwitchChannelPointsMiner.classes.Settings import Settings


class Campaign(object):
    __slots__ = [
        "id",
        "game",
        "name",
        "status",
        "in_inventory",
        "end_at",
        "start_at",
        "dt_match",
        "drops",
        "channels",
    ]

    def __init__(self, dict):
        self.id = dict["id"]
        self.game = dict.get("game")
        self.name = dict["name"]
        self.status = dict.get("status")
        allow_channels = (
            dict.get("allow", {}).get("channels") if dict.get("allow") else None
        )
        self.channels = [x["id"] for x in allow_channels] if allow_channels else []
        self.in_inventory = False

        self.end_at = parse_datetime(dict.get("endAt"))
        self.start_at = parse_datetime(dict.get("startAt"))
        self.dt_match = (
            self.start_at
            < datetime.now(timezone.utc).replace(tzinfo=None)
            < self.end_at
            if (self.start_at and self.end_at)
            else False
        )

        self.drops = [Drop(x) for x in (dict.get("timeBasedDrops") or [])]

    def __repr__(self):
        return f"Campaign(id={self.id}, name={self.name}, game={self.game}, in_inventory={self.in_inventory})"

    def __str__(self):
        game_name = (
            self.game.get("displayName", "") if isinstance(self.game, dict) else ""
        )
        return (
            f"{self.name}, Game: {game_name} - Drops: {len(self.drops)} pcs. - In inventory: {self.in_inventory}"
            if getattr(Settings.logger, "less", False)
            else self.__repr__()
        )

    def clear_drops(self):
        self.drops = list(filter(lambda x: x.dt_match and not x.is_claimed, self.drops))

    def __eq__(self, other):
        if isinstance(other, Campaign):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

    def sync_drops(self, drops, callback):
        for drop in drops:
            for i in range(len(self.drops)):
                current_id = self.drops[i].id
                if drop["id"] == current_id:
                    self.drops[i].update(drop["self"])
                    if self.drops[i].is_claimable:
                        claimed = callback(self.drops[i])
                        self.drops[i].is_claimed = claimed
                    break
