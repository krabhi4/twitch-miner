class CommunityGoal(object):
    __slots__ = [
        "goal_id",
        "title",
        "is_in_stock",
        "points_contributed",
        "amount_needed",
        "per_stream_user_maximum_contribution",
        "status",
    ]

    def __init__(
        self,
        goal_id,
        title,
        is_in_stock,
        points_contributed,
        amount_needed,
        per_stream_user_maximum_contribution,
        status,
    ):
        self.goal_id = goal_id
        self.title = title
        self.is_in_stock = is_in_stock
        self.points_contributed = points_contributed
        self.amount_needed = amount_needed
        self.per_stream_user_maximum_contribution = per_stream_user_maximum_contribution
        self.status = status

    def __eq__(self, other):
        if isinstance(other, CommunityGoal):
            return self.goal_id is not None and self.goal_id == other.goal_id
        return False

    def __repr__(self) -> str:
        return f"CommunityGoal(goal_id: {self.goal_id}, title: {self.title}, is_in_stock: {self.is_in_stock}, points_contributed: {self.points_contributed}, amount_needed: {self.amount_needed}, per_stream_user_maximum_contribution: {self.per_stream_user_maximum_contribution}, status: {self.status})"

    def amount_left(self):
        needed = (
            self.amount_needed if isinstance(self.amount_needed, (int, float)) else 0
        )
        contributed = (
            self.points_contributed
            if isinstance(self.points_contributed, (int, float))
            else 0
        )
        return needed - contributed

    @classmethod
    def from_gql(cls, gql_goal):
        return cls(
            gql_goal.get("id", ""),
            gql_goal.get("title", ""),
            gql_goal.get("isInStock", False),
            gql_goal.get("pointsContributed", 0),
            gql_goal.get("amountNeeded", 0),
            gql_goal.get("perStreamUserMaximumContribution", 0),
            gql_goal.get("status", ""),
        )

    @classmethod
    def from_pubsub(cls, pubsub_goal):
        return cls(
            pubsub_goal.get("id", ""),
            pubsub_goal.get("title", ""),
            pubsub_goal.get("is_in_stock", False),
            pubsub_goal.get("points_contributed", 0),
            pubsub_goal.get("goal_amount", 0),
            pubsub_goal.get("per_stream_maximum_user_contribution", 0),
            pubsub_goal.get("status", ""),
        )
