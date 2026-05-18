from __future__ import annotations

import time
from dataclasses import dataclass

from .database import connect, ensure_rate_limit_tables
from .mail_client import send_html
from .utils import canonical_customer_identity, sanitize_for_log


COOLDOWN_SECONDS = 60 * 60
SOFT_BACKOFF_SECONDS = 0.25


@dataclass(frozen=True)
class RateLimitConfig:
    soft_limit: int
    hard_limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    soft_exceeded: bool = False
    hard_exceeded: bool = False
    count: int = 0
    cooldown_start: int = 0
    cooldown_until: int = 0


RATE_LIMITS = {
    'storage': RateLimitConfig(soft_limit=120, hard_limit=200, window_seconds=60 * 60),
    'search': RateLimitConfig(soft_limit=30, hard_limit=60, window_seconds=60 * 60),
    'export_all': RateLimitConfig(soft_limit=3, hard_limit=3, window_seconds=24 * 60 * 60),
    'rejected_upload': RateLimitConfig(soft_limit=10, hard_limit=15, window_seconds=60 * 60),
    'zip_upload': RateLimitConfig(soft_limit=30, hard_limit=60, window_seconds=60 * 60),
    'mail_loop': RateLimitConfig(soft_limit=0, hard_limit=0, window_seconds=60 * 60),
}


def _now() -> int:
    return int(time.time())


def _config(action: str) -> RateLimitConfig:
    return RATE_LIMITS[action]


def check_rate_limit(
    sender: str,
    action: str,
    *,
    now: int | None = None,
    increment: bool = True,
) -> RateLimitResult:
    timestamp = _now() if now is None else int(now)
    sender_identity = canonical_customer_identity(sender)
    config = _config(action)
    window_start = timestamp - config.window_seconds

    conn = connect()
    try:
        ensure_rate_limit_tables(conn)
        conn.execute(
            'DELETE FROM rate_limit_events WHERE created_at < ?',
            (timestamp - 2 * 24 * 60 * 60,),
        )
        count = int(conn.execute(
            '''
            SELECT COUNT(*) AS count
            FROM rate_limit_events
            WHERE sender = ? AND action = ? AND created_at >= ?
            ''',
            (sender_identity, action, window_start),
        ).fetchone()['count'])

        row = conn.execute(
            '''
            SELECT cooldown_until, cooldown_start
            FROM rate_limit_cooldowns
            WHERE sender = ? AND action = ?
            ''',
            (sender_identity, action),
        ).fetchone()
        if row and int(row['cooldown_until'] or 0) > timestamp:
            return RateLimitResult(
                allowed=False,
                hard_exceeded=True,
                count=count,
                cooldown_start=int(row['cooldown_start'] or 0),
                cooldown_until=int(row['cooldown_until'] or 0),
            )

        if count >= config.hard_limit:
            cooldown_until = timestamp + COOLDOWN_SECONDS
            conn.execute(
                '''
                INSERT OR REPLACE INTO rate_limit_cooldowns
                (sender, action, cooldown_start, cooldown_until)
                VALUES (?, ?, ?, ?)
                ''',
                (sender_identity, action, timestamp, cooldown_until),
            )
            conn.commit()
            return RateLimitResult(
                allowed=False,
                hard_exceeded=True,
                count=count,
                cooldown_start=timestamp,
                cooldown_until=cooldown_until,
            )

        if increment:
            conn.execute(
                '''
                INSERT INTO rate_limit_events (sender, action, created_at)
                VALUES (?, ?, ?)
                ''',
                (sender_identity, action, timestamp),
            )
            conn.commit()
            count += 1
        else:
            conn.commit()

        return RateLimitResult(
            allowed=True,
            soft_exceeded=count > config.soft_limit,
            count=count,
        )
    finally:
        conn.close()


def log_rate_limit_warning(sender: str, action: str, result: RateLimitResult) -> None:
    print(
        "rate limit soft threshold exceeded"
        f" | sender={sanitize_for_log(canonical_customer_identity(sender))}"
        f" | action={sanitize_for_log(action)}"
        f" | count={result.count}"
    )


def log_rate_limit_block(sender: str, action: str, result: RateLimitResult) -> None:
    print(
        "rate limit hard threshold exceeded"
        f" | sender={sanitize_for_log(canonical_customer_identity(sender))}"
        f" | action={sanitize_for_log(action)}"
        f" | count={result.count}"
        f" | cooldown_start={result.cooldown_start}"
        f" | cooldown_until={result.cooldown_until}"
    )


def apply_rate_limit_or_reply(sender: str, action: str) -> bool:
    result = check_rate_limit(sender, action)
    if result.hard_exceeded:
        log_rate_limit_block(sender, action, result)
        send_html(
            canonical_customer_identity(sender),
            'Probeer het later opnieuw',
            '''
            Hoi,<br><br>
            Er zijn tijdelijk erg veel verzoeken ontvangen vanaf dit e-mailadres.
            Probeer het later opnieuw.<br><br>
            Groet,<br>
            Bewaarhet
            ''',
        )
        return False
    if result.soft_exceeded:
        log_rate_limit_warning(sender, action, result)
        time.sleep(SOFT_BACKOFF_SECONDS)
    return True
