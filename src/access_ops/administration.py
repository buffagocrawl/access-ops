"""Explicit local process-owner authority and validated CSV policy updates."""
import csv
from dataclasses import asdict, fields
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import re

from .config import ConfigurationError, SUPPORTED_ACCESS_LEVELS, load_configuration
from .models import AccessPolicy, Application, ApproverType, Decision


def require_owner(configuration, actor):
    employee = configuration.employee(actor)
    if (employee is None or employee.status != "active" or employee.department != "Operations"
            or employee.title not in {"Operations Director", "IT Security Analyst"}):
        raise ValueError("Only an active mocked Operations Director or IT Security Analyst may perform this action.")


def policy_values(policy):
    return {key: sorted(value) if isinstance(value, frozenset) else value
            for key, value in asdict(policy).items()}


class PolicyAdministration:
    EDITABLE = {"eligible_departments", "eligible_titles", "decision", "approver_type", "approver_id",
                "temporary_allowed", "max_duration_days", "permanent_allowed", "enabled"}

    def __init__(self, directory, database):
        self.directory = Path(directory)
        self.database = database

    def revision(self):
        digest = hashlib.sha256()
        for filename in ("employees.csv", "applications.csv", "access_policies.csv"):
            digest.update((self.directory / filename).read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def _candidate(self, policy_id, changes, actor, expected_revision, staging):
        if self.revision() != expected_revision:
            raise ConfigurationError("Configuration changed since review. Reload and validate again.")
        config = load_configuration(self.directory)
        require_owner(config, actor)
        original = next((p for p in config.policies if p.policy_id == policy_id), None)
        if original is None or not isinstance(changes, dict) or set(changes) - self.EDITABLE:
            raise ConfigurationError("Select an existing policy and edit only supported fields.")
        before = policy_values(original)
        after = dict(before, **changes)
        for key in ("temporary_allowed", "permanent_allowed", "enabled"):
            if type(after[key]) is not bool:
                raise ConfigurationError(f"{key} must be a boolean.")
        if type(after["max_duration_days"]) is not int or after["max_duration_days"] < 0:
            raise ConfigurationError("Maximum duration must be a nonnegative integer.")
        for key, employee_field in (("eligible_departments", "department"), ("eligible_titles", "title")):
            known = {getattr(e, employee_field) for e in config.employees}
            known.update(v for p in config.policies for v in getattr(p, key))
            values = after[key]
            if (not isinstance(values, (list, tuple)) or not values or any(not isinstance(v, str) for v in values)
                    or len(values) != len(set(values)) or not set(values) <= known | {"*"}
                    or ("*" in values and len(values) != 1)):
                raise ConfigurationError(f"{key}: select known values or '*' alone.")
            after[key] = sorted(values)
        if after == before:
            raise ConfigurationError("No policy values changed.")
        after["policy_version"] = original.policy_version + 1
        shutil.copyfile(self.directory / "employees.csv", staging / "employees.csv")
        shutil.copyfile(self.directory / "applications.csv", staging / "applications.csv")
        with (staging / "access_policies.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=[f.name for f in fields(AccessPolicy)])
            writer.writeheader()
            for policy in config.policies:
                values = after if policy.policy_id == policy_id else policy_values(policy)
                writer.writerow({k: ";".join(v) if isinstance(v, list) else
                                 str(v).lower() if type(v) is bool else v for k, v in values.items()})
            file.flush()
            os.fsync(file.fileno())
        candidate = load_configuration(staging)
        updated = next(p for p in candidate.policies if p.policy_id == policy_id)
        if updated.decision == Decision.EXCEPTION_REVIEW and updated.approver_type not in (
                ApproverType.APPLICATION_OWNER, ApproverType.IT_SECURITY):
            raise ConfigurationError("Exception policies require a configured application-owner or IT-security reviewer.")
        if updated.enabled and updated.approver_type == ApproverType.MANAGER:
            for employee in candidate.employees:
                if (employee.status == "active"
                        and ("*" in updated.eligible_departments or employee.department in updated.eligible_departments)
                        and ("*" in updated.eligible_titles or employee.title in updated.eligible_titles)):
                    manager = candidate.employee(employee.manager_slack_id)
                    if manager is None or manager.status != "active" or manager.slack_user_id == employee.slack_user_id:
                        raise ConfigurationError("Every eligible employee must have an active, distinct manager.")
        return before, policy_values(updated)

    def _write_catalog(self, applications, policies, staging):
        shutil.copyfile(self.directory / "employees.csv", staging / "employees.csv")
        with (staging / "applications.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=[f.name for f in fields(Application)])
            writer.writeheader()
            for application in applications:
                writer.writerow({"application": application.application, "enabled": str(application.enabled).lower()})
        with (staging / "access_policies.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=[f.name for f in fields(AccessPolicy)])
            writer.writeheader()
            for policy in policies:
                values = policy_values(policy)
                writer.writerow({k: ";".join(v) if isinstance(v, list) else str(v).lower() if type(v) is bool else v for k, v in values.items()})

    def _lifecycle(self, application, actor, expected_revision, enabled, confirmed=True, create=None, preview=False, active_grants=None):
        if not confirmed:
            raise ConfigurationError("Confirm this application lifecycle change before saving.")
        if self.revision() != expected_revision:
            raise ConfigurationError("Configuration changed since review. Reload and validate again.")
        config = load_configuration(self.directory)
        require_owner(config, actor)
        current = config.application(application)
        if create is not None:
            if not isinstance(application, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,60}", application):
                raise ConfigurationError("Application name is required and may contain letters, numbers, spaces, underscores, or hyphens.")
            if current is not None:
                raise ConfigurationError("Application already exists.")
            levels = create.get("access_levels") if isinstance(create, dict) else None
            changes = create.get("policy") if isinstance(create, dict) else None
            if not isinstance(levels, list) or not levels or len(levels) != len(set(levels)) or not set(levels) <= SUPPORTED_ACCESS_LEVELS:
                raise ConfigurationError("Choose one or more supported access levels.")
            if not isinstance(changes, dict) or set(changes) - self.EDITABLE:
                raise ConfigurationError("Choose supported policy fields.")
            apps = list(config.applications) + [Application(application, enabled)]
            policies = list(config.policies)
            for level in levels:
                policy_id = "APP-" + re.sub(r"[^A-Z0-9]+", "-", application.upper()).strip("-") + "-" + level.upper()
                if any(p.policy_id == policy_id for p in policies):
                    raise ConfigurationError("Generated policy ID conflicts with an existing policy.")
                values = {"policy_id": policy_id, "application": application, "access_level": level,
                          "policy_version": 1, **changes}
                policies.append(AccessPolicy(**values))
            subject = f"APPLICATION:{application}"
            outcome = "APPLICATION_ADD"
            before = {"application": application, "exists": False}
        else:
            if current is None:
                raise ConfigurationError("Application not found.")
            if current.enabled == enabled:
                raise ConfigurationError("Application is already in that state.")
            apps = [Application(a.application, enabled if a.application == application else a.enabled) for a in config.applications]
            policies = list(config.policies)
            subject = f"APPLICATION:{application}"
            outcome = "APPLICATION_REENABLED" if enabled else "APPLICATION_DISABLED"
            before = {"application": application, "enabled": current.enabled,
                      "active_grants": active_grants}
        with tempfile.TemporaryDirectory(dir=self.directory) as temp:
            staging = Path(temp)
            self._write_catalog(apps, policies, staging)
            candidate = load_configuration(staging)
            after_app = candidate.application(application)
            after = {"application": application, "enabled": after_app.enabled,
                     "policies": [policy_values(p) for p in candidate.policies if p.application == application]}
            if preview:
                return before, after
            self.database.config_event(subject, actor, outcome + "_STARTED", before, after)
            if self.revision() != expected_revision:
                raise ConfigurationError("Configuration changed before save. Reload and validate again.")
            os.replace(staging / "applications.csv", self.directory / "applications.csv")
            os.replace(staging / "access_policies.csv", self.directory / "access_policies.csv")
        self.database.config_event(subject, actor, outcome + "_SUCCEEDED", before, after)
        return before, after

    def preview_application(self, application, access_levels, policy, actor, expected_revision, enabled=True):
        return self._lifecycle(application, actor, expected_revision, enabled, create={"access_levels": access_levels, "policy": policy}, preview=True)

    def create_application(self, application, access_levels, policy, actor, expected_revision, enabled=True):
        try:
            return self._lifecycle(application, actor, expected_revision, enabled, create={"access_levels": access_levels, "policy": policy})
        except Exception:
            self.database.config_event(f"APPLICATION:{application}", actor, "APPLICATION_ADD_REJECTED_OR_FAILED", None, None)
            raise

    def set_application_enabled(self, application, enabled, actor, expected_revision, confirmed=False, active_grants=None):
        action = "APPLICATION_REENABLED" if enabled else "APPLICATION_DISABLED"
        try:
            return self._lifecycle(application, actor, expected_revision, enabled, confirmed=confirmed, active_grants=active_grants)
        except Exception:
            self.database.config_event(f"APPLICATION:{application}", actor, action + "_REJECTED_OR_FAILED", None, None)
            raise

    def preview(self, policy_id, changes, actor, expected_revision):
        with tempfile.TemporaryDirectory(dir=self.directory) as staging:
            return self._candidate(policy_id, changes, actor, expected_revision, Path(staging))

    def save(self, policy_id, changes, actor, expected_revision):
        """Revalidate at save; durable intent precedes CSV replacement."""
        before = after = None
        try:
            with tempfile.TemporaryDirectory(dir=self.directory) as staging:
                staging = Path(staging)
                before, after = self._candidate(policy_id, changes, actor, expected_revision, staging)
                self.database.config_event(policy_id, actor, "SAVE_STARTED", before, after)
                # Serial local usage; detect stale preview again immediately before replacement.
                if self.revision() != expected_revision:
                    raise ConfigurationError("Configuration changed before save. Reload and validate again.")
                os.replace(staging / "access_policies.csv", self.directory / "access_policies.csv")
        except Exception:
            self.database.config_event(policy_id, actor, "SAVE_REJECTED_OR_FAILED", before, after)
            raise
        # If this fails, SAVE_STARTED remains durable. Do not report confirmed success.
        self.database.config_event(policy_id, actor, "SAVE_SUCCEEDED", before, after)
        return after
