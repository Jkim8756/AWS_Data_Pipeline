-- One row per unique employee name found across all processed timesheets.

{{
  config(materialized='table')
}}

select
    {{ dbt_utils.generate_surrogate_key(['employee_name']) }} as employee_key,
    employee_name,
    employee_id,
    min(pay_period_start)   as first_seen_period,
    max(pay_period_end)     as last_seen_period,
    count(distinct document_id) as total_documents,
    max(doc_created_at)     as last_processed_at
from {{ ref('stg_document_pages') }}
where employee_name is not null
group by employee_name, employee_id
