from datetime import datetime

from TwitchChannelPointsMiner.classes.Settings import Settings
from TwitchChannelPointsMiner.utils import percentage


def parse_datetime(datetime_str):
    if not datetime_str or not isinstance(datetime_str, str):
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(datetime_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


class Drop(object):
    __slots__ = [
        "id",
        "name",
        "benefit",
        "minutes_required",
        "has_preconditions_met",
        "current_minutes_watched",
        "drop_instance_id",
        "is_claimed",
        "is_claimable",
        "percentage_progress",
        "end_at",
        "start_at",
        "dt_match",
        "is_printable",
    ]

    def __init__(self, data):
        self.id = data.get("id")
        self.name = data.get("name", "")
        self.benefit = ", ".join(
            list(
                set(
                    [
                        bf["benefit"]["name"]
                        for bf in data.get("benefitEdges", [])
                        if isinstance(bf, dict) and bf.get("benefit", {}).get("name")
                    ]
                )
            )
        )
        self.minutes_required = data.get("requiredMinutesWatched", 0)

        self.has_preconditions_met = None
        self.current_minutes_watched = 0
        self.drop_instance_id = None
        self.is_claimed = False
        self.is_claimable = False
        self.is_printable = False
        self.percentage_progress = 0

        self.end_at = parse_datetime(data.get("endAt"))
        self.start_at = parse_datetime(data.get("startAt"))
        self.dt_match = (
            self.start_at < datetime.now() < self.end_at
            if (self.start_at and self.end_at)
            else False
        )

    def update(
        self,
        progress,
    ):
        self.has_preconditions_met = progress.get("hasPreconditionsMet")

        updated_percentage = percentage(
            progress.get("currentMinutesWatched", 0), self.minutes_required
        )
        quarter = round((updated_percentage / 25), 4).is_integer()
        self.is_printable = progress.get(
            "currentMinutesWatched", 0
        ) > self.current_minutes_watched and (
            (
                updated_percentage > self.percentage_progress
                and quarter
                and self.current_minutes_watched != 0
            )
            or (
                progress.get("currentMinutesWatched", 0) == 1
                and self.current_minutes_watched == 0
            )
        )

        self.current_minutes_watched = progress.get("currentMinutesWatched", 0)
        self.drop_instance_id = progress.get("dropInstanceID")
        self.is_claimed = progress.get("isClaimed", False)
        self.is_claimable = not self.is_claimed and self.drop_instance_id is not None
        self.percentage_progress = updated_percentage

    def __repr__(self):
        return f"Drop(id={self.id}, name={self.name}, benefit={self.benefit}, minutes_required={self.minutes_required}, has_preconditions_met={self.has_preconditions_met}, current_minutes_watched={self.current_minutes_watched}, percentage_progress={self.percentage_progress}%, drop_instance_id={self.drop_instance_id}, is_claimed={self.is_claimed})"

    def __str__(self):
        return (
            f"{self.name} ({self.benefit}) {self.current_minutes_watched}/{self.minutes_required} ({self.percentage_progress}%)"
            if getattr(Settings.logger, "less", False)
            else self.__repr__()
        )

    def progress_bar(self):
        pct = max(0, min(100, int(self.percentage_progress)))
        progress = pct // 2
        remaining = 50 - progress
        return f"|{'█' * progress}{' ' * remaining}|\t{self.percentage_progress}% [{self.current_minutes_watched}/{self.minutes_required}]"

    def __eq__(self, other):
        if isinstance(other, Drop):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)
