from django.db import models


class AccountMembershipRole(models.TextChoices):
    VIEWER = "viewer", "Viewer"
    MEMBER = "member", "Member"
    ADMIN = "admin", "Admin"
    OWNER = "owner", "Owner"


class AccountAccessMode(models.TextChoices):
    READ_ONLY = "read_only", "Read only"
    WATCH_ONLY = "watch_only", "Watch only"
    FULL = "full", "Full"


class BalanceChangeReason:
    TX_CREATED = "tx_created"
    TX_MOVED = "tx_moved"
    TX_UPDATED = "tx_updated"
    TX_DELETED = "tx_deleted"
    TX_FALLBACK_RECALC = "tx_fallback_recalc"
