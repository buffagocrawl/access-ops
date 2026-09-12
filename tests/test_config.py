"""Configuration failures must prevent any configuration from being returned."""
import csv
import shutil
from pathlib import Path

import pytest

from access_ops.config import ConfigurationError, load_configuration
from access_ops.models import Decision, EmployeeStatus

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config_dir(tmp_path):
    for name in ("employees.csv", "access_policies.csv"):
        shutil.copyfile(ROOT / "config" / name, tmp_path / name)
    return tmp_path


def edit_row(directory, filename, index, **changes):
    path = directory / filename
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        headers = reader.fieldnames
        rows = list(reader)
    rows[index].update(changes)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_valid_configuration_and_employee_lookup(config_dir):
    config = load_configuration(config_dir)
    assert len(config.employees) == 11
    assert len(config.policies) == 12
    assert config.employee("UDEMO001").department == "Engineering"
    assert config.employee("UDEMO004").status == EmployeeStatus.INACTIVE
    assert config.employee("UDEMO009").manager_slack_id is None
    assert config.employee("udemo001") is None
    assert config.employee("unknown") is None
    assert config.policies[0].decision == Decision.AUTO_APPROVE
    assert config.policies[0].max_duration_days == 30
    assert config.policies[0].eligible_titles == frozenset({"*"})


@pytest.mark.parametrize("filename", ["employees.csv", "access_policies.csv"])
@pytest.mark.parametrize("damage", ["missing", "empty", "header_only", "column", "duplicate_header", "extra_cell", "short_row", "quote", "encoding"])
def test_malformed_files(config_dir, filename, damage):
    path = config_dir / filename
    lines = path.read_text().splitlines()
    if damage == "missing":
        path.unlink()
    elif damage == "encoding":
        path.write_bytes(b"\xff\xfe\x00")
    else:
        content = {
            "empty": "",
            "header_only": lines[0] + "\n",
            "column": "wrong," + "\n".join(lines),
            "duplicate_header": lines[0] + "," + lines[0].split(",")[0] + "\n" + lines[1],
            "extra_cell": lines[0] + "\n" + lines[1] + ",extra",
            "short_row": lines[0] + "\n" + ",".join(lines[1].split(",")[:-1]),
            "quote": lines[0] + '\n"unterminated',
        }[damage]
        path.write_text(content)
    with pytest.raises(ConfigurationError, match=filename):
        load_configuration(config_dir)


@pytest.mark.parametrize("changes, message", [
    ({"name": " "}, "name is required"),
    ({"status": "yes"}, "EmployeeStatus"),
    ({"slack_user_id": "UDEMO002"}, "duplicate slack_user_id"),
    ({"manager_slack_id": "missing"}, "manager must reference"),
    ({"manager_slack_id": "UDEMO001"}, "manager must reference"),
    ({"manager_slack_id": "UDEMO004"}, "manager is inactive"),
])
def test_invalid_employees(config_dir, changes, message):
    edit_row(config_dir, "employees.csv", 0, **changes)
    with pytest.raises(ConfigurationError, match=message):
        load_configuration(config_dir)


@pytest.mark.parametrize("index, changes, message", [
    (0, {"enabled": "yes"}, "enabled must be"),
    (0, {"policy_version": "0"}, "policy_version must be"),
    (0, {"max_duration_days": "1.5"}, "max_duration_days must be"),
    (0, {"application": "Zoom"}, "unsupported"),
    (0, {"access_level": "read"}, "unsupported"),
    (0, {"decision": "ALLOW"}, "Decision"),
    (0, {"approver_type": "BOSS"}, "ApproverType"),
    (0, {"eligible_departments": "*;Engineering"}, "semicolon"),
    (0, {"eligible_titles": "Engineer;Engineer"}, "semicolon"),
    (0, {"eligible_titles": "Engineer;"}, "semicolon"),
    (0, {"decision": "APPROVAL_REQUIRED"}, "inconsistent"),
    (0, {"approver_id": "UDEMO005"}, "approver_id is required only"),
    (2, {"approver_id": ""}, "approver_id is required only"),
    (2, {"approver_id": "missing"}, "active employee"),
    (2, {"approver_id": "UDEMO004"}, "active employee"),
    (0, {"max_duration_days": "0"}, "positive"),
    (3, {"permanent_allowed": "true"}, "REJECT"),
    (0, {"temporary_allowed": "false", "max_duration_days": "0", "permanent_allowed": "false"}, "must allow a duration"),
    (4, {"permanent_allowed": "true"}, "Admin requires"),
    (4, {"max_duration_days": "30"}, "Admin requires"),
    (1, {"policy_id": "GH-READ-ENG"}, "duplicate policy_id"),
])
def test_invalid_policies(config_dir, index, changes, message):
    edit_row(config_dir, "access_policies.csv", index, **changes)
    with pytest.raises(ConfigurationError, match=message):
        load_configuration(config_dir)


@pytest.mark.parametrize("departments", ["*", "Engineering;Product", "Engineering"])
def test_ambiguous_policies(config_dir, departments):
    edit_row(config_dir, "access_policies.csv", 2, eligible_departments=departments)
    with pytest.raises(ConfigurationError, match="GH-WRITE-ENG and GH-WRITE-EXCEPTION"):
        load_configuration(config_dir)


def test_overlap_detected_without_matching_current_employee(config_dir):
    edit_row(config_dir, "access_policies.csv", 1, eligible_departments="Future", eligible_titles="Future Title")
    edit_row(config_dir, "access_policies.csv", 2, eligible_departments="Future", eligible_titles="Future Title")
    with pytest.raises(ConfigurationError, match="ambiguous"):
        load_configuration(config_dir)


def test_disjoint_titles_and_disabled_overlap_are_valid(config_dir):
    edit_row(config_dir, "access_policies.csv", 1, eligible_titles="Software Engineer")
    edit_row(config_dir, "access_policies.csv", 2, eligible_departments="Engineering", eligible_titles="Engineering Manager")
    load_configuration(config_dir)
    edit_row(config_dir, "access_policies.csv", 2, eligible_titles="*", enabled="false")
    load_configuration(config_dir)


def test_missing_application(config_dir):
    path = config_dir / "access_policies.csv"
    path.write_text("\n".join(line for line in path.read_text().splitlines() if ",Notion," not in line))
    with pytest.raises(ConfigurationError, match="five demo applications"):
        load_configuration(config_dir)


def test_bom_and_surrounding_whitespace(config_dir):
    edit_row(config_dir, "employees.csv", 0, name=" Alice Engineer ")
    path = config_dir / "employees.csv"
    path.write_text(path.read_text(), encoding="utf-8-sig")
    assert load_configuration(config_dir).employee("UDEMO001").name == "Alice Engineer"
