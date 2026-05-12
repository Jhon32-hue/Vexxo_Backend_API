from common.domain_events import EventNames


class BudgetDomainEventTypes:
    BUDGET_CREATED = EventNames.BUDGET_CREATED
    BUDGET_UPDATED = EventNames.BUDGET_UPDATED
    BUDGET_DELETED = EventNames.BUDGET_DELETED


__all__ = ["BudgetDomainEventTypes"]
