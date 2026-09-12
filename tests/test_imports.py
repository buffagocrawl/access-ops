"""Scaffold import checks only; these do not verify workflow behavior."""

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "access_ops",
        "access_ops.models",
        "access_ops.config",
        "access_ops.policy_engine",
        "access_ops.workflow",
        "access_ops.approvals",
        "access_ops.audit",
        "access_ops.database",
        "access_ops.notifications",
        "access_ops.integrations",
        "access_ops.integrations.mock_okta",
    ],
)
def test_module_imports(module_name):
    """Each planned module can be imported through the configured src layout."""
    import_module(module_name)
