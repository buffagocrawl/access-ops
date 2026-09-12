"""Selection checks do not perform approvals or provision access."""
from dataclasses import replace
from pathlib import Path

import pytest

from access_ops.config import ConfigurationError, load_configuration
from access_ops.models import Decision
from access_ops.policy_engine import match_policy


@pytest.fixture
def config():
    return load_configuration(Path(__file__).resolve().parents[1] / "config")


@pytest.mark.parametrize("employee, app, level, policy_id, decision", [
    ("UDEMO001", "GitHub", "Read", "GH-READ-ENG", Decision.AUTO_APPROVE),
    ("UDEMO001", "GitHub", "Write", "GH-WRITE-ENG", Decision.APPROVAL_REQUIRED),
    ("UDEMO002", "GitHub", "Write", "GH-WRITE-EXCEPTION", Decision.EXCEPTION_REVIEW),
    ("UDEMO003", "GitHub", "Write", "GH-WRITE-EXCEPTION", Decision.EXCEPTION_REVIEW),
    ("UDEMO011", "GitHub", "Write", "GH-WRITE-REJECT", Decision.REJECT),
    ("UDEMO005", "GitHub", "Admin", "GH-ADMIN-ENG", Decision.APPROVAL_REQUIRED),
    ("UDEMO011", "Figma", "View", "FIGMA-VIEW", Decision.AUTO_APPROVE),
    ("UDEMO002", "Figma", "Editor", "FIGMA-EDITOR", Decision.AUTO_APPROVE),
    ("UDEMO009", "Notion", "Standard", "NOTION-STANDARD", Decision.AUTO_APPROVE),
    ("UDEMO003", "Salesforce", "Standard", "SF-STANDARD", Decision.APPROVAL_REQUIRED),
    ("UDEMO001", "Salesforce", "Standard", "SF-STANDARD-REJECT", Decision.REJECT),
    ("UDEMO008", "Snowflake", "Read", "SNOW-READ", Decision.APPROVAL_REQUIRED),
    ("UDEMO001", "Snowflake", "Write", "SNOW-WRITE", Decision.APPROVAL_REQUIRED),
])
def test_exact_demo_matches(config, employee, app, level, policy_id, decision):
    policy = match_policy(config, employee, app, level)
    assert policy.policy_id == policy_id
    assert policy.decision == decision
    assert match_policy(replace(config, policies=tuple(reversed(config.policies))), employee, app, level) == policy


@pytest.mark.parametrize("employee, app, level", [
    ("UDEMO001", "github", "Read"),
    ("UDEMO001", "GitHub", "read"),
    ("UDEMO001", "GitHub ", "Read"),
    ("UDEMO001", "Unknown", "Read"),
    ("UDEMO001", "GitHub", "Owner"),
    ("UDEMO002", "GitHub", "Read"),
    ("UDEMO001", "GitHub", "Admin"),
    ("UDEMO011", "Figma", "Editor"),
])
def test_unmatched_returns_no_policy(config, employee, app, level):
    assert match_policy(config, employee, app, level) is None


@pytest.mark.parametrize("employee", ["unknown", "UDEMO004"])
def test_unknown_and_inactive_employees_fail(config, employee):
    with pytest.raises(ValueError, match="known, active employee"):
        match_policy(config, employee, "Notion", "Standard")


def test_disabled_rule_does_not_match(config):
    policies = tuple(replace(p, enabled=False) for p in config.policies)
    assert match_policy(replace(config, policies=policies), "UDEMO001", "GitHub", "Read") is None


def test_runtime_ambiguity_fails_even_if_loader_bypassed(config):
    config = replace(config, policies=config.policies + (config.policies[0],))
    with pytest.raises(ConfigurationError, match="Multiple policies"):
        match_policy(config, "UDEMO001", "GitHub", "Read")
