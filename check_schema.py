import psycopg2
from services.api.core.config import get_settings

conn = psycopg2.connect(get_settings().DB_URL)
cur = conn.cursor()

# Check RLS
cur.execute("SELECT relname, relrowsecurity FROM pg_class WHERE relname IN ('evidence_documents', 'pipeline_jobs', 'document_extractions', 'emission_inputs', 'emission_results', 'reports', 'chemical_processes');")
print("RLS status:")
for row in cur.fetchall():
    print(row)

# Check reports table
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'reports' ORDER BY ordinal_position;")
cols = cur.fetchall()
print("\nReports columns:")
for col in cols:
    print(col)

conn.close()
