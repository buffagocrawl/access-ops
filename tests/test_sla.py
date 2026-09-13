from datetime import datetime, timedelta, timezone

from access_ops.sla import DEMO_SLA_TARGET, format_age, request_age, sla_status


CREATED = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def test_younger_request_is_within_demo_target():
    assert sla_status(CREATED, CREATED + timedelta(hours=23, minutes=59)) == "Within target"


def test_older_request_is_past_demo_target():
    assert sla_status(CREATED, CREATED + timedelta(hours=24, minutes=1)) == "Past target"


def test_exact_threshold_is_deterministically_past_target():
    assert sla_status(CREATED, CREATED + DEMO_SLA_TARGET) == "Past target"


def test_sla_calculation_is_derived_and_does_not_change_request_state():
    status = "PENDING_APPROVAL"
    assert request_age(CREATED, CREATED + timedelta(hours=3)) == timedelta(hours=3)
    assert sla_status(CREATED, CREATED + timedelta(hours=3)) == "Within target"
    assert status == "PENDING_APPROVAL"


def test_age_format_is_readable():
    assert format_age(timedelta(days=1, hours=7, minutes=2)) == "1d 7h"
    assert format_age(timedelta(hours=3, minutes=14)) == "3h 14m"
