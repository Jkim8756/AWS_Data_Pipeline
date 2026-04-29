# Project: Timesheet ETL Pipeline

## Purpose

This project automates the extraction and transformation of handwritten timesheet data for a cleaning company. Non-technical staff scan paper timesheets and upload them as PDFs to an S3 bucket. The pipeline picks those files up automatically, uses Claude's vision capabilities to read the handwritten content, and writes structured employee attendance and hours data into a PostgreSQL database. The end goal is a ready-to-use database with clean, analytics-ready data that downstream teams can query without any manual data entry or cleanup.

---

## Agentic Structure

The pipeline is composed of three sequential agents or processing layers, each with a distinct responsibility:

**1. Ingestion Agent (AWS Lambda + Claude Vision)**
A Lambda function is triggered whenever a new PDF lands in the upload S3 bucket. It reads the PDF, sends it to Claude Sonnet via the Anthropic API, and instructs Claude to extract all timesheet fields from every page — including project metadata, employee names, EINs, scheduled and actual hours, absence flags, and schedule change flags. Claude returns a structured JSON object. The raw JSON is immediately saved to a second S3 bucket for audit and replay purposes before any database writes occur.

**2. Storage Agent (Supabase PostgreSQL)**
The Lambda function writes the extracted JSON into two Supabase tables. One table tracks each uploaded PDF as a document record. The other stores one row per employee per working day, capturing every field extracted by Claude. Upsert logic ensures that re-uploading the same PDF does not create duplicates.

**3. Transformation Agent (dbt Cloud)**
A dbt Cloud project runs on a daily schedule against the Supabase database. It performs three transformations: a staging model that cleans and standardizes the raw entries (trimming whitespace, normalizing casing, filtering out rows with missing dates or names); a dimension table that deduplicated employees by their EIN; and a fact table that aggregates hours worked per employee per project per day.

---

## Infrastructure

The pipeline is provisioned with Terraform. The core AWS resources are two S3 buckets (one for incoming PDFs, one for raw JSON output), an SQS queue with a dead-letter queue for reliable Lambda triggering, and a container-based Lambda function. The Lambda is packaged as a Docker image to cleanly handle Python dependencies. Environment variables supply database credentials and the Anthropic API key; in production the API key should be stored in AWS Secrets Manager rather than as a plaintext environment variable.

---

## Expected Outcome

A fully populated Supabase PostgreSQL database with two layers of tables:

- **Raw tables** (`timesheet_documents`, `timesheet_entries`) — one row per PDF and one row per employee per day, populated automatically whenever a PDF is uploaded.
- **Clean analytics tables** (`stg_timesheet_entries`, `dim_employees`, `fct_daily_hours`) — produced by dbt, with normalized names, typed columns, and deduplicated employee records.

The database is ready to use for payroll verification, attendance reporting, and project-level labor analysis without any manual data entry.

---

## Key Design Decisions

- Claude Sonnet is used over Haiku for better accuracy on mixed print-and-handwritten content.
- SQS decouples S3 events from Lambda invocations so retries and failure handling are automatic.
- Raw JSON is always saved to S3 before the database write, enabling replay if the schema changes or a write fails.
- Time values are stored as raw text in the database and normalized only in the dbt staging layer, because handwritten time formats are inconsistent across pages.
- Supabase's Session Pooler on port 5432 is used for Lambda connections; switching to Transaction Pooler on port 6543 is the scaling path if concurrent invocations exhaust the connection limit.
