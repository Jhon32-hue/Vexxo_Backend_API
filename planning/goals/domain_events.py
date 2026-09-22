from common.domain_events import EventNames


class GoalDomainEventTypes:
    GOAL_CREATED = EventNames.GOAL_CREATED
    GOAL_UPDATED = EventNames.GOAL_UPDATED
    STATUS_CHANGED = EventNames.GOAL_STATUS_CHANGED
    CONTRIBUTION_RECORDED = EventNames.GOAL_CONTRIBUTION_RECORDED
    CONTRIBUTION_REVERSED = EventNames.GOAL_CONTRIBUTION_REVERSED
    PROGRESS_UPDATED = EventNames.GOAL_PROGRESS_UPDATED
    MILESTONE_ACHIEVED = "goals.milestone.achieved.v1"
    MILESTONE_REOPENED = "goals.milestone.reopened.v1"
