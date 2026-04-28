-- One row per employee per date — explodes the entries JSONB array.

{{
  config(materialized='table')
}}

with entries as (

    select
        employee_name,
        employee_id,
        department,
        pay_period_start,
        pay_period_end,
        document_id,
        page_number,
        ocr_model,
        (entry.value ->> 'date')::date        as work_date,
        (entry.value ->> 'day_of_week')        as day_of_week,
        (entry.value ->> 'time_in')            as time_in,
        (entry.value ->> 'time_out')           as time_out,
        (entry.value ->> 'break_minutes')::int as break_minutes,
        (entry.value ->> 'hours_worked')::numeric as hours_worked,
        (entry.value ->> 'notes')              as notes
    from {{ ref('stg_document_pages') }},
         jsonb_array_elements(entries_json) as entry(value)
    where entries_json is not null

)

select
    {{ dbt_utils.generate_surrogate_key(['employee_name', 'work_date']) }} as daily_key,
    employee_name,
    employee_id,
    department,
    pay_period_start,
    pay_period_end,
    work_date,
    day_of_week,
    time_in,
    time_out,
    break_minutes,
    hours_worked,
    notes,
    document_id,
    page_number,
    ocr_model
from entries
where work_date is not null
