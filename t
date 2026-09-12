warning: in the working copy of '.env.example', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'README.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'requirements.txt', LF will be replaced by CRLF the next time Git touches it
[1mdiff --git a/.env.example b/.env.example[m
[1mindex d1add1f..6fdb3d7 100644[m
[1m--- a/.env.example[m
[1m+++ b/.env.example[m
[36m@@ -4,5 +4,5 @@[m
 ACCESS_OPS_DB_PATH=access_ops.db[m
 [m
 # Synthetic directory and policy configuration files[m
[31m-EMPLOYEES_CSV_PATH=data/employees.csv[m
[31m-ACCESS_POLICIES_CSV_PATH=data/access_policies.csv[m
[32m+[m[32mEMPLOYEES_CSV_PATH=config/employees.csv[m
[32m+[m[32mACCESS_POLICIES_CSV_PATH=config/access_policies.csv[m
[1mdiff --git a/README.md b/README.md[m
[1mindex 584a858..11c4ac6 100644[m
[1m--- a/README.md[m
[1m+++ b/README.md[m
[36m@@ -12,7 +12,7 @@[m [mAn agentic natural-language intake architecture is documented for comparison and[m
 [m
 ### Implemented behavior[m
 [m
[31m-The initial configuration foundation contains synthetic employees and explicit access policies in `config/`. Application code, configuration loading/validation, and tests have not been started; these files do not enforce access decisions yet.[m
[32m+[m[32mThe configuration foundation contains synthetic employees and explicit access policies in `config/`. The Python package scaffold and pytest import checks are in place. Source modules contain documentation placeholders only; configuration loading/validation and all workflow behavior remain unimplemented. No access decisions are enforced yet.[m
 [m
 ### Planned behavior[m
 [m
[36m@@ -33,12 +33,31 @@[m [mSlack identity, forms, messages, approval actions, and alerts; employee-director[m
 [m
 ```text[m
 access-ops/[m
[31m-|-- config/         Synthetic trusted employees and access policies[m
[31m-├── Planning/       Architecture, scope, blueprint, and implementation decisions[m
[31m-├── .env.example    Safe local configuration template[m
[31m-├── .gitignore      Local and generated-file exclusions[m
[31m-├── README.md       Project overview and status[m
[31m-└── requirements.txt Dependency placeholder for future implementation[m
[32m+[m[32m├── Planning/              Existing architecture and locked scope documents[m
[32m+[m[32m├── config/[m
[32m+[m[32m│   ├── employees.csv       Existing synthetic trusted directory[m
[32m+[m[32m│   └── access_policies.csv Existing policy catalog[m
[32m+[m[32m├── src/access_ops/[m
[32m+[m[32m│   ├── __init__.py[m
[32m+[m[32m│   ├── models.py           Data representations[m
[32m+[m[32m│   ├── config.py           CSV loading and validation[m
[32m+[m[32m│   ├── policy_engine.py    Deterministic policy evaluation[m
[32m+[m[32m│   ├── workflow.py         UI-independent orchestration[m
[32m+[m[32m│   ├── approvals.py        Single-reviewer authorization[m
[32m+[m[32m│   ├── audit.py            Append-style audit events[m
[32m+[m[32m│   ├── database.py         SQLite persistence[m
[32m+[m[32m│   ├── notifications.py    Safe Slack-style messages[m
[32m+[m[32m│   └── integrations/[m
[32m+[m[32m│       ├── __init__.py[m
[32m+[m[32m│       └── mock_okta.py    Mock provider boundary[m
[32m+[m[32m├── tests/[m
[32m+[m[32m│   └── test_imports.py     Scaffold imports only[m
[32m+[m[32m├── AGENTS.md               Repository instructions[m
[32m+[m[32m├── .env.example            Safe local configuration template[m
[32m+[m[32m├── .gitignore              Local and generated-file exclusions[m
[32m+[m[32m├── pytest.ini             Test discovery and src import path[m
[32m+[m[32m├── README.md              Project overview and setup[m
[32m+[m[32m└── requirements.txt       pytest dependency[m
 ```[m
 [m
 ## Development and setup[m
[36m@@ -58,7 +77,21 @@[m [maccess-ops/[m
 [m
 These are prototype policy assumptions, not Customer.io policies. Design and Customer Success are configured for future synthetic records without requiring additional employees now. The Blueprint lists several admin roles and UI features; the locked scope limits this foundation to one elevated example (GitHub Admin), with no UI. Unmatched combinations remain manual-review cases, not implicit approvals or implicit exception grants.[m
 [m
[31m-Implementation setup instructions will be added when the application structure, dependencies, and runnable commands are established. Until then, there is no application command to run. Future local development is expected to use a Python virtual environment and synthetic/mock data defined by the implementation.[m
[32m+[m[32m### Local scaffold checks (Python 3.12)[m
[32m+[m
[32m+[m[32mReuse the existing `.venv`. If setting up a fresh checkout, create it with a Python 3.12 interpreter (`python -m venv .venv`). From the repository root in PowerShell:[m
[32m+[m
[32m+[m[32m```powershell[m
[32m+[m[32m.\.venv\Scripts\python.exe --version[m
[32m+[m[32m.\.venv\Scripts\python.exe -m pip install -r requirements.txt[m
[32m+[m[32m.\.venv\Scripts\python.exe -m pytest[m
[32m+[m[32m```[m
[32m+[m
[32m+[m[32m`pytest.ini` makes `src/` importable during tests and collects tests from `tests/`; no package installation or activation is needed for these commands. SQLite (`sqlite3`) and CSV support use Python's standard library. Streamlit is deferred until the demo interface is built. All future business logic belongs in `src/access_ops/`, independently of Streamlit.[m
[32m+[m
[32m+[m[32mThere is no runnable application yet. Models, CSV validation, policy evaluation, approvals, provisioning, SQLite schema, auditing, notifications, retries, duplicate protection, expiration, and revocation are deliberately deferred. The planned `app.py`, `seed.py`, and behavior test modules will be added when their respective implementation phases begin. The `.env.example` paths match the existing configuration, but environment-file loading is not implemented.[m
[32m+[m
[32m+[m[32mThe import checks verify the scaffold only. Normal, approval, exception, unauthorized, duplicate, provisioning-failure, expiration, and revocation-failure scenarios still need implementation and behavioral tests before the core prototype can be considered complete.[m
 [m
 Do not commit credentials, tokens, passwords, API keys, or local `.env` files. The `.env` file is gitignored; use `.env.example` as the safe template.[m
 [m
[1mdiff --git a/requirements.txt b/requirements.txt[m
[1mindex dd8c9a3..d1d26a5 100644[m
[1m--- a/requirements.txt[m
[1m+++ b/requirements.txt[m
[36m@@ -1,2 +1,2 @@[m
[31m-# Dependencies will be added when implementation decisions require them.[m
[31m-[m
[32m+[m[32m# Scaffold test dependency. SQLite and CSV support are in Python's standard library.[m
[32m+[m[32mpytest>=8,<9[m
