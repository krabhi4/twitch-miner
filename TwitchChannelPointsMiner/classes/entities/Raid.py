class Raid(object):
    __slots__ = ["raid_id", "target_login"]

    def __init__(self, raid_id, target_login):
        self.raid_id = raid_id
        self.target_login = target_login

    def __repr__(self):
        return f"Raid(raid_id={self.raid_id}, target_login={self.target_login})"

    def __eq__(self, other):
        if isinstance(other, Raid):
            return self.raid_id == other.raid_id
        return False

    def __hash__(self):
        return hash(self.raid_id)
