from .app_domain_error import RateLimitedError


class TooManyRequestsError(RateLimitedError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            'too_many_requests',
            'Too many attempts, please wait a moment',
            {'retry_after': max(1, retry_after), 'minutes': max(1, -(-retry_after // 60))},
        )
