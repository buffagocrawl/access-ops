"""Validate the local application catalog and all policy rows before use."""
import csv
from dataclasses import dataclass, fields
from itertools import combinations
from pathlib import Path
import re

from .models import AccessPolicy, Application, ApproverType, Decision, Employee, EmployeeStatus

# Deliberately bounded vocabulary, while application names and configured combinations are data-driven.
APPLICATION_ACCESS = {
    "GitHub": {"Read", "Write", "Admin"}, "Figma": {"View", "Editor"},
    "Notion": {"Standard"}, "Salesforce": {"Standard"}, "Snowflake": {"Read", "Write"},
}
SUPPORTED_ACCESS_LEVELS = frozenset(level for levels in APPLICATION_ACCESS.values() for level in levels)
_APPLICATION_NAME = re.compile(r"[A-Za-z][A-Za-z0-9 _-]{0,60}\Z")

class ConfigurationError(ValueError): pass

@dataclass(frozen=True)
class Configuration:
    employees: tuple[Employee, ...]
    policies: tuple[AccessPolicy, ...]
    applications: tuple[Application, ...] = ()
    it_operations_recipient: str = "#it-operations"
    def employee(self, slack_user_id): return next((e for e in self.employees if e.slack_user_id == slack_user_id), None)
    def application(self, value):
        catalog = self.applications or tuple(Application(p.application, True) for p in self.policies)
        return next((a for a in catalog if a.application == value), None)
    @property
    def application_access(self):
        catalog = {a.application: set(APPLICATION_ACCESS.get(a.application, set())) for a in (self.applications or tuple(Application(p.application, True) for p in self.policies))}
        for policy in self.policies:
            catalog.setdefault(policy.application, set()).add(policy.access_level)
        return {application: frozenset(levels) for application, levels in catalog.items()}

def _rows(path, model, optional):
    required={field.name for field in fields(model)}
    try:
        with Path(path).open(encoding='utf-8-sig', newline='') as file:
            reader=csv.DictReader(file, strict=True); headers=reader.fieldnames or []
            if len(headers)!=len(set(headers)) or set(headers)!=required: raise ConfigurationError(f"{path}: invalid columns")
            found=False
            for row in reader:
                found=True; location=f"{path}: row {reader.line_num}"
                if None in row or None in row.values(): raise ConfigurationError(f"{location}: wrong number of cells")
                row={key:value.strip() for key,value in row.items()}
                for key in sorted(required-optional):
                    if not row[key]: raise ConfigurationError(f"{location}: {key} is required")
                yield location,row
            if not found: raise ConfigurationError(f"{path}: at least one data row is required")
    except (OSError, UnicodeError, csv.Error) as error: raise ConfigurationError(f"{path}: cannot read configuration: {error}") from error

def _boolean(value, field):
    if value not in {'true','false'}: raise ValueError(f'{field} must be true or false')
    return value=='true'
def _integer(value, field, minimum):
    if not value.isascii() or not value.isdecimal() or int(value)<minimum: raise ValueError(f'{field} must be an integer >= {minimum}')
    return int(value)
def _selectors(value, field):
    parts=[p.strip() for p in value.split(';')]
    if '' in parts or len(parts)!=len(set(parts)) or ('*' in parts and len(parts)!=1): raise ValueError(f"{field} must be distinct semicolon-separated values or '*' alone")
    return frozenset(parts)
def _overlap(left,right): return '*' in left or '*' in right or bool(left&right)
def _validate_policy(p, employees):
    if p.access_level not in SUPPORTED_ACCESS_LEVELS: raise ValueError('unsupported access_level')
    review=p.decision in {Decision.APPROVAL_REQUIRED,Decision.EXCEPTION_REVIEW}
    if review != (p.approver_type != ApproverType.NONE): raise ValueError('decision and approver_type are inconsistent')
    fixed=p.approver_type in {ApproverType.APPLICATION_OWNER,ApproverType.IT_SECURITY}
    if fixed != bool(p.approver_id): raise ValueError('approver_id is required only for APPLICATION_OWNER or IT_SECURITY')
    if fixed and (p.approver_id not in employees or employees[p.approver_id].status != EmployeeStatus.ACTIVE): raise ValueError('approver_id must reference an active employee')
    if p.temporary_allowed != (p.max_duration_days>0): raise ValueError('temporary_allowed requires positive max_duration_days; otherwise use zero')
    if p.decision == Decision.REJECT:
        if p.temporary_allowed or p.permanent_allowed: raise ValueError('REJECT must allow neither temporary nor permanent access')
    elif not p.temporary_allowed and not p.permanent_allowed: raise ValueError('non-rejection policy must allow a duration')
    if p.access_level=='Admin' and (p.decision != Decision.APPROVAL_REQUIRED or p.approver_type != ApproverType.IT_SECURITY or not p.temporary_allowed or p.permanent_allowed or p.max_duration_days>7): raise ValueError('Admin requires IT_SECURITY approval and temporary-only access up to 7 days')

def load_configuration(directory='config'):
    directory=Path(directory); employees=[]
    for location,row in _rows(directory/'employees.csv',Employee,{'manager_slack_id'}):
        try:
            row['status']=EmployeeStatus(row['status']); row['manager_slack_id']=row['manager_slack_id'] or None; item=Employee(**row)
            if any(e.slack_user_id==item.slack_user_id for e in employees): raise ValueError(f'duplicate slack_user_id {item.slack_user_id}')
            employees.append(item)
        except ValueError as error: raise ConfigurationError(f'{location}: {error}') from error
    by_id={e.slack_user_id:e for e in employees}
    for employee in employees:
        manager=employee.manager_slack_id
        if manager and (manager not in by_id or manager==employee.slack_user_id): raise ConfigurationError('employees.csv: manager must reference another employee')
        if manager and employee.status==EmployeeStatus.ACTIVE and by_id[manager].status!=EmployeeStatus.ACTIVE: raise ConfigurationError('employees.csv: manager is inactive')
    applications=[]
    legacy_catalog = not (directory / 'applications.csv').exists()
    for location,row in ([] if legacy_catalog else _rows(directory/'applications.csv', Application, set())):
        try:
            row['enabled']=_boolean(row['enabled'],'enabled'); item=Application(**row)
            if not _APPLICATION_NAME.fullmatch(item.application): raise ValueError('application must be a supported name')
            if any(a.application.casefold()==item.application.casefold() for a in applications): raise ValueError('duplicate application')
            applications.append(item)
        except ValueError as error: raise ConfigurationError(f'{location}: {error}') from error
    app_names={a.application for a in applications}; policies=[]
    for location,row in _rows(directory/'access_policies.csv',AccessPolicy,{'approver_id'}):
        try:
            for key in ('temporary_allowed','permanent_allowed','enabled'): row[key]=_boolean(row[key],key)
            for key in ('eligible_departments','eligible_titles'): row[key]=_selectors(row[key],key)
            row['max_duration_days']=_integer(row['max_duration_days'],'max_duration_days',0); row['policy_version']=_integer(row['policy_version'],'policy_version',1)
            row['decision']=Decision(row['decision']); row['approver_type']=ApproverType(row['approver_type']); row['approver_id']=row['approver_id'] or None
            item=AccessPolicy(**row)
            if legacy_catalog and item.application not in APPLICATION_ACCESS: raise ValueError('unsupported demo application/access_level')
            if not legacy_catalog and item.application not in app_names: raise ValueError('policy application must exist in applications.csv')
            _validate_policy(item,by_id)
            if any(p.policy_id==item.policy_id for p in policies): raise ValueError(f'duplicate policy_id {item.policy_id}')
            policies.append(item)
        except ValueError as error: raise ConfigurationError(f'{location}: {error}') from error
    if legacy_catalog:
        if {p.application for p in policies} != set(APPLICATION_ACCESS): raise ConfigurationError('access_policies.csv: catalog must contain exactly the five demo applications')
        applications = [Application(application, True) for application in APPLICATION_ACCESS]
        app_names = {a.application for a in applications}
    if {p.application for p in policies} != app_names: raise ConfigurationError('every application requires at least one policy')
    for left,right in combinations((p for p in policies if p.enabled),2):
        if left.application==right.application and left.access_level==right.access_level and _overlap(left.eligible_departments,right.eligible_departments) and _overlap(left.eligible_titles,right.eligible_titles): raise ConfigurationError(f'ambiguous enabled policies {left.policy_id} and {right.policy_id}')
    return Configuration(tuple(employees),tuple(policies),tuple(applications))
