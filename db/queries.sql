-- 1. All documents with current processing status
SELECT id, filename, job_status, textract_job_id, upload_time, created_at
FROM documents
ORDER BY created_at DESC;

-- 2. Page stats per document (page count, total words, average confidence)
SELECT
    d.filename,
    d.job_status,
    COUNT(p.id)              AS pages_processed,
    SUM(p.word_count)        AS total_words,
    SUM(p.line_count)        AS total_lines,
    ROUND(AVG(p.avg_confidence), 2) AS overall_avg_confidence
FROM documents d
LEFT JOIN pages p ON p.document_id = d.id
GROUP BY d.id, d.filename, d.job_status
ORDER BY d.created_at DESC;

-- 3. Documents that failed processing
SELECT id, filename, textract_job_id, created_at
FROM documents
WHERE job_status = 'FAILED'
ORDER BY created_at DESC;

-- 4. All pages for a specific document ordered by page number
-- Replace the UUID below with the actual document id
SELECT
    page_number,
    total_blocks,
    word_count,
    line_count,
    avg_confidence,
    min_confidence,
    max_confidence
FROM pages
WHERE document_id = '00000000-0000-0000-0000-000000000000'
ORDER BY page_number;

-- 5. Overall pipeline summary
SELECT
    COUNT(DISTINCT d.id)            AS total_documents,
    COUNT(DISTINCT d.id) FILTER (WHERE d.job_status = 'SUCCEEDED') AS succeeded,
    COUNT(DISTINCT d.id) FILTER (WHERE d.job_status = 'FAILED')    AS failed,
    COUNT(DISTINCT d.id) FILTER (WHERE d.job_status = 'SUBMITTED') AS in_progress,
    COUNT(p.id)                     AS total_pages,
    SUM(p.word_count)               AS total_words,
    ROUND(AVG(p.avg_confidence), 2) AS overall_avg_confidence
FROM documents d
LEFT JOIN pages p ON p.document_id = d.id;
