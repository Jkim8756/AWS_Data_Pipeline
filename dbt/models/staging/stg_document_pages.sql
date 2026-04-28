-- Staging model: flatten document_pages for downstream marts.
-- Explodes the structured_data JSONB → one row per employee per page.

{{
  config(materialized='view')
}}

with pages as (

    select
        dp.id              as page_id,
        dp.document_id,
        dp.page_number,
        dp.extracted_text,
        dp.word_count,
        dp.structured_data,
        dp.created_at      as page_created_at,
        d.file_name,
        d.s3_bucket,
        d.s3_key,
        d.ocr_model,
        d.status,
        d.created_at       as doc_created_at
    from {{ source('public', 'document_pages') }} dp
    join {{ source('public', 'documents') }}      d
        on d.id = dp.document_id
    where d.status = 'done'

),

exploded as (

    select
        p.page_id,
        p.document_id,
        p.page_number,
        p.file_name,
        p.s3_bucket,
        p.s3_key,
        p.ocr_model,
        p.doc_created_at,
        -- one row per employee on this page
        (emp.value ->> 'name')              as employee_name,
        (emp.value ->> 'employee_id')       as employee_id,
        (emp.value ->> 'total_hours')::numeric as total_hours,
        (emp.value ->> 'signature_present')::boolean as signature_present,
        (p.structured_data ->> 'pay_period_start')::date as pay_period_start,
        (p.structured_data ->> 'pay_period_end')::date   as pay_period_end,
        (p.structured_data ->> 'department')             as department,
        emp.value -> 'entries'              as entries_json
    from pages p,
         jsonb_array_elements(
             coalesce(p.structured_data -> 'employees', '[]'::jsonb)
         ) as emp(value)

)

select * from exploded
