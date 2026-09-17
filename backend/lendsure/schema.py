"""LendSure database schema — real relational tables, no giant JSON blobs for core facts."""
from __future__ import annotations

MODEL_VERSION = "lendsure-risk-v1.3"

DDL = """
CREATE TABLE IF NOT EXISTS ls_borrowers (
    borrower_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER, city TEXT, employment_type TEXT, employment_years REAL,
    monthly_income REAL, household_size INTEGER, dependents INTEGER,
    requested_amount REAL, tenure_months INTEGER, purpose TEXT, first_time_borrower INTEGER,
    prev_loans INTEGER, loans_repaid INTEGER, late_payments INTEGER, avg_delay_days REAL,
    defaults INTEGER, max_days_past_due INTEGER,
    avg_income_6m REAL, avg_expenses_6m REAL, avg_debt_6m REAL, income_volatility REAL,
    expense_trend REAL, debt_trend REAL, total_transactions_6m INTEGER,
    bounced_payments_6m INTEGER, disputed_txns_6m INTEGER,
    id_verification INTEGER, address_verification INTEGER, phone_verification INTEGER,
    bank_stmt_status INTEGER, income_doc_status INTEGER, doc_quality_score INTEGER,
    transaction_variance REAL, night_txn_ratio REAL, new_device_90d INTEGER, applications_30d INTEGER,
    address_changes_12m INTEGER, doc_avg_income REAL,
    vouches_count INTEGER, avg_vouch_trust REAL, community_tenure_years REAL,
    group_memberships INTEGER, guarantor_past_count INTEGER,
    account_age_months INTEGER, prev_lenders_count INTEGER, disputes_raised INTEGER, disputes_lost INTEGER,
    ontime_streak_months INTEGER, salary_credits_6m INTEGER, savings_balance REAL, existing_debt_accounts INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ls_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id TEXT NOT NULL,
    month INTEGER NOT NULL,
    label TEXT NOT NULL,
    income REAL, expenses REAL, debt REAL, transactions INTEGER,
    bounced INTEGER, disputed INTEGER,
    UNIQUE (borrower_id, month)
);
CREATE INDEX IF NOT EXISTS idx_ls_fin_b ON ls_financials (borrower_id);
CREATE TABLE IF NOT EXISTS ls_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    file_name TEXT NOT NULL,
    status TEXT NOT NULL,
    quality_score INTEGER,
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ls_doc_b ON ls_documents (borrower_id);
CREATE TABLE IF NOT EXISTS ls_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    risk_score REAL, risk_level TEXT,
    fraud_score REAL, fraud_risk TEXT,
    trust_score REAL, confidence REAL,
    decision TEXT,
    recommended_amount REAL, interest_rate REAL, duration_months INTEGER, monthly_payment REAL,
    ml_score REAL,
    risk_factors TEXT DEFAULT '[]',
    fraud_signals TEXT DEFAULT '[]',
    trust_factors TEXT DEFAULT '[]',
    input_snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_ls_an_b ON ls_analyses (borrower_id);
CREATE TABLE IF NOT EXISTS ls_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL UNIQUE,
    borrower_id TEXT NOT NULL,
    recommended_amount REAL, interest_rate REAL, duration_months INTEGER,
    monthly_payment REAL, total_repayment REAL, decision TEXT, rationale TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ls_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    sort INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ls_ev_a ON ls_evidence (analysis_id);
CREATE TABLE IF NOT EXISTS ls_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id TEXT NOT NULL,
    analysis_id INTEGER,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ls_au_b ON ls_audit (borrower_id);
CREATE TABLE IF NOT EXISTS ls_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ls_api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used TEXT,
    revoked INTEGER DEFAULT 0
);
"""

# ---- Loan lifecycle, repayments, jobs, notifications, events, cases, perf ----
# Appended after the core DDL; all CREATE TABLE IF NOT EXISTS so boot-time
# execution is a safe migration on existing databases.
LIFECYCLE_DDL = """
CREATE TABLE IF NOT EXISTS ls_loan_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id TEXT NOT NULL,
    analysis_id INTEGER,
    amount REAL NOT NULL CHECK (amount > 0),
    interest_rate REAL NOT NULL CHECK (interest_rate >= 0 AND interest_rate <= 60),
    duration_months INTEGER NOT NULL CHECK (duration_months >= 1 AND duration_months <= 84),
    purpose TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    idempotency_key TEXT UNIQUE,
    requested_by TEXT DEFAULT '',
    reviewer TEXT DEFAULT '',
    review_note TEXT DEFAULT '',
    decided_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lr_b ON ls_loan_requests (borrower_id);
CREATE INDEX IF NOT EXISTS idx_lr_s ON ls_loan_requests (status);
CREATE TABLE IF NOT EXISTS ls_loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL UNIQUE,
    borrower_id TEXT NOT NULL,
    principal REAL NOT NULL,
    interest_rate REAL NOT NULL,
    duration_months INTEGER NOT NULL,
    emi REAL NOT NULL,
    disbursed_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    outstanding_principal REAL NOT NULL,
    total_paid REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ln_b ON ls_loans (borrower_id);
CREATE TABLE IF NOT EXISTS ls_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL,
    n INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    principal REAL NOT NULL,
    interest REAL NOT NULL,
    total_due REAL NOT NULL,
    paid REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'UPCOMING',
    paid_at TEXT,
    UNIQUE (loan_id, n)
);
CREATE INDEX IF NOT EXISTS idx_sch_l ON ls_schedule (loan_id);
CREATE TABLE IF NOT EXISTS ls_repayments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL,
    schedule_id INTEGER,
    amount REAL NOT NULL CHECK (amount > 0),
    method TEXT DEFAULT 'manual',
    idempotency_key TEXT UNIQUE,
    recorded_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rep_l ON ls_repayments (loan_id);
CREATE TABLE IF NOT EXISTS ls_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    ref_type TEXT DEFAULT '',
    ref_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    payload TEXT DEFAULT '{}',
    result TEXT DEFAULT '',
    error TEXT DEFAULT '',
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_s ON ls_jobs (status);
CREATE TABLE IF NOT EXISTS ls_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audience TEXT NOT NULL DEFAULT 'role:lender',
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    link TEXT DEFAULT '',
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_not_a ON ls_notifications (audience, is_read);
CREATE TABLE IF NOT EXISTS ls_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    actor TEXT DEFAULT '',
    data TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ev_e ON ls_events (entity, entity_id);
CREATE INDEX IF NOT EXISTS idx_ev_t ON ls_events (created_at);
CREATE TABLE IF NOT EXISTS ls_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'investigation',
    status TEXT NOT NULL DEFAULT 'OPEN',
    borrower_id TEXT DEFAULT '',
    evidence TEXT DEFAULT '{}',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS ls_borrower_perf (
    borrower_id TEXT PRIMARY KEY,
    loans_completed INTEGER DEFAULT 0,
    repayments_on_time INTEGER DEFAULT 0,
    repayments_missed INTEGER DEFAULT 0,
    amount_repaid REAL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ls_doc_files (
    doc_id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mime TEXT DEFAULT '',
    data BLOB,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ls_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id TEXT NOT NULL,
    analysis_id INTEGER,
    model_id TEXT NOT NULL,
    proba REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pred_t ON ls_predictions (created_at);
CREATE TABLE IF NOT EXISTS ls_officers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    city TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_off_c ON ls_officers (city);
CREATE TABLE IF NOT EXISTS ls_case_transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    from_city TEXT DEFAULT '',
    to_city TEXT NOT NULL,
    requested_by TEXT DEFAULT '',
    decided_by TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'REQUESTED',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ct_c ON ls_case_transfers (case_id);
CREATE TABLE IF NOT EXISTS ls_grievances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL UNIQUE,
    borrower_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    subject TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'NORMAL',
    status TEXT NOT NULL DEFAULT 'OPEN',
    assigned_to TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_gr_t ON ls_grievances (ticket_id);
CREATE INDEX IF NOT EXISTS idx_gr_s ON ls_grievances (status);
CREATE TABLE IF NOT EXISTS ls_grievance_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grievance_id INTEGER NOT NULL,
    actor TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gn_g ON ls_grievance_notes (grievance_id);
"""

# Column migrations for existing tables (each applied once, failures ignored).
# Column migrations. Each entry is (name, sql) — applied once via the
# ls_migrations ledger in app.init_db (own transaction, rollback on failure).
INTELLIGENCE_DDL = """
CREATE TABLE IF NOT EXISTS ls_intelligence_access (
    borrower_id TEXT NOT NULL REFERENCES ls_borrowers(borrower_id) ON DELETE CASCADE,
    principal TEXT NOT NULL,
    demo_only INTEGER NOT NULL DEFAULT 0 CHECK (demo_only IN (0,1)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (borrower_id, principal),
    CHECK (demo_only=0 OR borrower_id GLOB 'DEMO-*')
);
CREATE INDEX IF NOT EXISTS idx_intelligence_access_principal ON ls_intelligence_access(principal);
CREATE TABLE IF NOT EXISTS ls_intelligence_consents (
    id TEXT PRIMARY KEY,
    borrower_id TEXT NOT NULL,
    principal TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('credit','cashflow')),
    mode TEXT NOT NULL CHECK (mode IN ('sandbox','attested')),
    status TEXT NOT NULL CHECK (status IN ('sandbox','attested','revoked')),
    purpose TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (borrower_id, principal) REFERENCES ls_intelligence_access(borrower_id, principal) ON DELETE CASCADE,
    UNIQUE (id, borrower_id, principal),
    CHECK (mode!='attested' OR scope='cashflow')
);
CREATE INDEX IF NOT EXISTS idx_intelligence_consent_owner ON ls_intelligence_consents(borrower_id, principal, scope, expires_at);
CREATE TABLE IF NOT EXISTS ls_intelligence_credit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id TEXT NOT NULL,
    principal TEXT NOT NULL,
    consent_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('DEMO/SANDBOX','CREDIT BUREAU')),
    provider TEXT NOT NULL,
    report_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (consent_id, borrower_id, principal) REFERENCES ls_intelligence_consents(id, borrower_id, principal) ON DELETE CASCADE,
    UNIQUE (consent_id, source, provider)
);
CREATE INDEX IF NOT EXISTS idx_intelligence_credit_owner ON ls_intelligence_credit(borrower_id, principal, fetched_at);
CREATE TABLE IF NOT EXISTS ls_intelligence_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id TEXT NOT NULL,
    principal TEXT NOT NULL,
    consent_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('BANK-DERIVED','DECLARED BY BORROWER','DEMO/SANDBOX')),
    provider TEXT NOT NULL,
    record_date TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('in','out')),
    amount REAL NOT NULL CHECK (amount>0 AND amount<=1000000000000),
    category TEXT NOT NULL,
    balance REAL CHECK (balance BETWEEN -1000000000000 AND 1000000000000),
    fingerprint TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (consent_id, borrower_id, principal) REFERENCES ls_intelligence_consents(id, borrower_id, principal) ON DELETE CASCADE,
    UNIQUE (borrower_id, principal, source, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_intelligence_records_consent ON ls_intelligence_records(consent_id);
CREATE INDEX IF NOT EXISTS idx_intelligence_records_owner_date ON ls_intelligence_records(borrower_id, principal, source, record_date);
"""

LS_MIGRATIONS = [
    ("intelligence.v1", INTELLIGENCE_DDL),
    ("borrowers.phone", "ALTER TABLE ls_borrowers ADD COLUMN phone TEXT DEFAULT ''"),
    ("borrowers.email", "ALTER TABLE ls_borrowers ADD COLUMN email TEXT DEFAULT ''"),
    ("borrowers.address_line", "ALTER TABLE ls_borrowers ADD COLUMN address_line TEXT DEFAULT ''"),
    ("borrowers.device_id", "ALTER TABLE ls_borrowers ADD COLUMN device_id TEXT DEFAULT ''"),
    ("borrowers.bank_account", "ALTER TABLE ls_borrowers ADD COLUMN bank_account TEXT DEFAULT ''"),
    ("documents.pipeline_status", "ALTER TABLE ls_documents ADD COLUMN pipeline_status TEXT DEFAULT 'PENDING'"),
    ("documents.pipeline_evidence", "ALTER TABLE ls_documents ADD COLUMN pipeline_evidence TEXT DEFAULT '[]'"),
    ("documents.ocr_status", "ALTER TABLE ls_documents ADD COLUMN ocr_status TEXT DEFAULT 'NOT_AVAILABLE'"),
    ("documents.scan_status", "ALTER TABLE ls_documents ADD COLUMN scan_status TEXT DEFAULT 'NOT_AVAILABLE'"),
    ("documents.content_hash", "ALTER TABLE ls_documents ADD COLUMN content_hash TEXT DEFAULT ''"),
    ("cases.assigned_to", "ALTER TABLE ls_cases ADD COLUMN assigned_to TEXT DEFAULT ''"),
    ("cases.city", "ALTER TABLE ls_cases ADD COLUMN city TEXT DEFAULT ''"),
    ("cases.transfer_status", "ALTER TABLE ls_cases ADD COLUMN transfer_status TEXT DEFAULT 'NONE'"),
    ("analyses.risk_json_cols",
     "ALTER TABLE ls_analyses ADD COLUMN risk_factors TEXT DEFAULT '[]';"
     "ALTER TABLE ls_analyses ADD COLUMN fraud_signals TEXT DEFAULT '[]';"
     "ALTER TABLE ls_analyses ADD COLUMN trust_factors TEXT DEFAULT '[]';"
     "ALTER TABLE ls_analyses ADD COLUMN ml_score TEXT DEFAULT '[]'"),
    # Retired v1 tables (confirmed empty, never populated by the ls_* engine).
    ("drop-legacy-v1-tables",
     "DROP TABLE IF EXISTS borrowers;DROP TABLE IF EXISTS documents;DROP TABLE IF EXISTS vouches;"
     "DROP TABLE IF EXISTS loans;DROP TABLE IF EXISTS fraud_flags;DROP TABLE IF EXISTS audit_logs"),
    ("sessions.auth_columns",
     "ALTER TABLE sessions ADD COLUMN email TEXT DEFAULT '';"),
    ("sessions.last_active", "ALTER TABLE sessions ADD COLUMN last_active TEXT"),
    ("sessions.ip", "ALTER TABLE sessions ADD COLUMN ip TEXT DEFAULT ''"),
    ("sessions.ua_hash", "ALTER TABLE sessions ADD COLUMN ua_hash TEXT DEFAULT ''"),
    ("sessions.device_hash", "ALTER TABLE sessions ADD COLUMN device_hash TEXT DEFAULT ''"),
    ("sessions.remember", "ALTER TABLE sessions ADD COLUMN remember INTEGER DEFAULT 0"),
    ("devices.table",
     "CREATE TABLE IF NOT EXISTS ls_devices (email TEXT NOT NULL, device_hash TEXT NOT NULL,"
     " verified INTEGER DEFAULT 0, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,"
     " PRIMARY KEY (email, device_hash))"),
    ("audit.chain_columns",
     "ALTER TABLE ls_audit ADD COLUMN prev_hash TEXT DEFAULT '';"),
    ("audit.chain_hash_col",
     "ALTER TABLE ls_audit ADD COLUMN chain_hash TEXT DEFAULT '';"),
    ("users.phone",
     "ALTER TABLE users ADD COLUMN phone TEXT DEFAULT '';"),
    ("api_keys.expiry_scopes",
     "ALTER TABLE ls_api_keys ADD COLUMN expires_at TEXT DEFAULT '';"
     "ALTER TABLE ls_api_keys ADD COLUMN scopes TEXT DEFAULT 'read';"
     "UPDATE ls_api_keys SET scopes='admin' WHERE scopes='read';"),
]

DEFAULT_CONFIG = {
    "model_version": MODEL_VERSION,
    "risk_low_max": 35,
    "risk_medium_max": 65,
    "fraud_low_max": 30,
    "fraud_medium_max": 60,
    "interest_low": [8.0, 10.0],
    "interest_medium": [11.0, 15.0],
    "interest_high": [16.0, 20.0],
    "afford_base_mult": 2.0,
    "afford_trust_mult": 6.0,
    "max_tenure_months": 24,
    "high_risk_tenure_cap": 12,
    "manual_review_fraud_score": 60,
    "reject_risk_score": 80,
    "min_recommended_ratio": 0.6,
    "approve_trust_min": 70,
    "ml_blend": 0.5,
}
