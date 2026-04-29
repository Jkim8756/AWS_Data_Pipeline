-- Weekly summary: total hours per employee per ISO week.

{{
  config(materialized='table')
}}

select
    employee_name,
    employee_id,
    department,
    date_trunc('week', work_date)::date  as week_start,
    to_char(work_date, 'IYYY-IW')        as iso_week,
    count(*)                             as days_worked,
    sum(hours_worked)                    as total_hours,
    sum(break_minutes)                   as total_break_minutes,
    min(work_date)                       as first_day,
    max(work_date)                       as last_day,
    -- Flag weeks with more than 40 hours
    sum(hours_worked) > 40               as has_overtime,
    max(ocr_model)                       as ocr_model
from {{ ref('daily_hours') }}
where hours_worked is not null
group by
    employee_name,
    employee_id,
    department,
    date_trunc('week', work_date),
    to_char(work_date, 'IYYY-IW')
order by
    employee_name,
    week_start
