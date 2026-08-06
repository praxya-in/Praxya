-- Check 4: Did the extraction actually happen?
SELECT id, document_id, overall_confidence, is_human_reviewed, created_at
FROM document_extractions
ORDER BY created_at DESC
LIMIT 5;