CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS timesheet_entries (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file       TEXT        NOT NULL,
    textract_job_id   TEXT,
    work_date         DATE,
    project           TEXT,
    business_unit     TEXT,
    day_of_week       TEXT,
    weather           TEXT,
    staff_type        TEXT,
    row_no            INTEGER,
    job_task          TEXT,
    title             TEXT,
    employee_name     TEXT        NOT NULL,
    ein               TEXT,
    sched_start       TEXT,
    sched_end         TEXT,
    sched_hours       NUMERIC(5,2),
    actual_start      TEXT,
    lunch_out         TEXT,
    lunch_in          TEXT,
    actual_end        TEXT,
    hours_worked      NUMERIC(5,2),
    absent            BOOLEAN     NOT NULL DEFAULT FALSE,
    schedule_changed  BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_te_work_date    ON timesheet_entries(work_date);
CREATE INDEX IF NOT EXISTS idx_te_employee     ON timesheet_entries(employee_name);
CREATE INDEX IF NOT EXISTS idx_te_source_file  ON timesheet_entries(source_file);
