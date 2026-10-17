from datetime import timedelta

from app.worker import retry_delay


def test_retry_delay_is_exponential_and_capped() -> None:
    assert retry_delay(1) == timedelta(seconds=1)
    assert retry_delay(2) == timedelta(seconds=2)
    assert retry_delay(4) == timedelta(seconds=8)
    assert retry_delay(20) == timedelta(seconds=300)
