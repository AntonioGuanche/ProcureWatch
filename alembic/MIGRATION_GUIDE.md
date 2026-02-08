# Production Migration Guide

## Context

The migration chain (001→013) was squashed into `001_baseline.py`.
Two schema drift issues exist in production databases:

1. **notice_documents**: Missing 11 pipeline columns (migration 010 dropped+recreated the table without columns from 007)
2. **filters**: Model updated but no migration was created (old: cpv_code/region/min_value/max_value → new: cpv_prefixes/countries/buyer_keywords)

## Step 1: Fix schema drift (run on prod BEFORE stamping)

### PostgreSQL

```sql
-- Fix notice_documents: add pipeline columns (idempotent)
DO $$
BEGIN
    -- Download pipeline
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='local_path') THEN
        ALTER TABLE notice_documents ADD COLUMN local_path VARCHAR(2000);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='content_type') THEN
        ALTER TABLE notice_documents ADD COLUMN content_type VARCHAR(100);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='file_size') THEN
        ALTER TABLE notice_documents ADD COLUMN file_size INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='sha256') THEN
        ALTER TABLE notice_documents ADD COLUMN sha256 VARCHAR(64);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='downloaded_at') THEN
        ALTER TABLE notice_documents ADD COLUMN downloaded_at TIMESTAMP;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='download_status') THEN
        ALTER TABLE notice_documents ADD COLUMN download_status VARCHAR(20);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='download_error') THEN
        ALTER TABLE notice_documents ADD COLUMN download_error TEXT;
    END IF;
    -- Text extraction pipeline
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='extracted_text') THEN
        ALTER TABLE notice_documents ADD COLUMN extracted_text TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='extracted_at') THEN
        ALTER TABLE notice_documents ADD COLUMN extracted_at TIMESTAMP;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='extraction_status') THEN
        ALTER TABLE notice_documents ADD COLUMN extraction_status VARCHAR(20);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='notice_documents' AND column_name='extraction_error') THEN
        ALTER TABLE notice_documents ADD COLUMN extraction_error TEXT;
    END IF;

    -- Fix filters: rename/add/drop columns
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='filters' AND column_name='cpv_code') THEN
        ALTER TABLE filters RENAME COLUMN cpv_code TO cpv_prefixes;
        ALTER TABLE filters ALTER COLUMN cpv_prefixes TYPE VARCHAR(200);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='filters' AND column_name='region') THEN
        ALTER TABLE filters RENAME COLUMN region TO countries;
        ALTER TABLE filters ALTER COLUMN countries TYPE VARCHAR(100);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='filters' AND column_name='buyer_keywords') THEN
        ALTER TABLE filters ADD COLUMN buyer_keywords VARCHAR(500);
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='filters' AND column_name='min_value') THEN
        ALTER TABLE filters DROP COLUMN min_value;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='filters' AND column_name='max_value') THEN
        ALTER TABLE filters DROP COLUMN max_value;
    END IF;
    -- Resize name column
    ALTER TABLE filters ALTER COLUMN name TYPE VARCHAR(200);
END $$;
```

## Step 2: Stamp Alembic to baseline

After running the SQL fix above:

```bash
alembic stamp 001
```

This tells Alembic the database is now at revision `001` (the squashed baseline).

## Fresh installs

For new databases, just run:

```bash
alembic upgrade head
```

This creates all 9 tables from scratch via `001_baseline.py`.

## Verification

After migration, verify:

```sql
-- Check notice_documents has pipeline columns
SELECT column_name FROM information_schema.columns
WHERE table_name = 'notice_documents'
ORDER BY ordinal_position;

-- Check filters has new columns
SELECT column_name FROM information_schema.columns
WHERE table_name = 'filters'
ORDER BY ordinal_position;

-- Check alembic version
SELECT * FROM alembic_version;
-- Should show: 001
```
