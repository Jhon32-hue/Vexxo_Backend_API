import hashlib
import hmac
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from security.models import SecurityThrottleBucket


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


def hash_rate_limit_subject(value: str) -> str:
    key = str(getattr(settings, "SECURITY_THROTTLE_HASH_KEY", "") or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(key, str(value or "").strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()


def consume_rate_limit(*, scope: str, subject: str, limit: int, window_seconds: int) -> RateLimitResult:
    if not subject:
        return RateLimitResult(True, max(0, limit), 0)
    now = timezone.now()
    subject_hash = hash_rate_limit_subject(subject)
    with transaction.atomic():
        try:
            bucket = SecurityThrottleBucket.objects.select_for_update().get(scope=scope, subject_hash=subject_hash)
        except SecurityThrottleBucket.DoesNotExist:
            try:
                with transaction.atomic():
                    bucket = SecurityThrottleBucket.objects.create(
                        scope=scope,
                        subject_hash=subject_hash,
                        window_started_at=now,
                    )
            except IntegrityError:
                bucket = SecurityThrottleBucket.objects.select_for_update().get(scope=scope, subject_hash=subject_hash)
        if bucket.blocked_until and bucket.blocked_until > now:
            retry = max(1, int((bucket.blocked_until - now).total_seconds()))
            return RateLimitResult(False, 0, retry)
        if (now - bucket.window_started_at).total_seconds() >= window_seconds:
            bucket.window_started_at = now
            bucket.request_count = 0
            bucket.blocked_until = None
        bucket.request_count += 1
        allowed = bucket.request_count <= limit
        retry = 0
        if not allowed:
            bucket.blocked_until = bucket.window_started_at + timedelta(seconds=window_seconds)
            retry = max(1, int((bucket.blocked_until - now).total_seconds()))
        bucket.save(update_fields=["window_started_at", "request_count", "blocked_until", "updated_at"])
        return RateLimitResult(allowed, max(0, limit - bucket.request_count), retry)


def check_cooldown(*, scope: str, subject: str, cooldown_seconds: int) -> RateLimitResult:
    return consume_rate_limit(scope=f"{scope}:cooldown", subject=subject, limit=1, window_seconds=cooldown_seconds)
