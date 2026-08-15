import pytest

from zcoder.domain.services.outbox_policy import transition_after_failure


def test_failure_remains_pending_below_attempt_budget():
    transition = transition_after_failure(current_attempts=0, max_attempts=3)

    assert transition.attempts == 1
    assert transition.status == "PENDING"


def test_failure_becomes_dead_exactly_at_attempt_budget():
    transition = transition_after_failure(current_attempts=2, max_attempts=3)

    assert transition.attempts == 3
    assert transition.status == "DEAD"


def test_failure_stays_dead_when_called_past_budget():
    transition = transition_after_failure(current_attempts=3, max_attempts=3)

    assert transition.attempts == 4
    assert transition.status == "DEAD"


@pytest.mark.parametrize(
    ("current_attempts", "max_attempts", "message"),
    [
        (-1, 3, "current_attempts must be >= 0"),
        (0, 0, "max_attempts must be >= 1"),
        (0, -1, "max_attempts must be >= 1"),
    ],
)
def test_failure_transition_rejects_invalid_budgets(current_attempts, max_attempts, message):
    with pytest.raises(ValueError, match=message):
        transition_after_failure(current_attempts=current_attempts, max_attempts=max_attempts)
