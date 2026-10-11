-- Additive migration: never remove messages, documents, chunks, or volumes.
-- Existing 384-dimensional vectors remain untouched. An incompatible populated
-- table requires a deliberate re-embedding plan and fails this transaction.
DO $$
DECLARE
    embedding_type TEXT;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod)
      INTO embedding_type
      FROM pg_attribute a
     WHERE a.attrelid = 'document_chunks'::regclass
       AND a.attname = 'embedding' AND NOT a.attisdropped;
    IF embedding_type IS DISTINCT FROM 'vector(384)' THEN
        IF EXISTS (SELECT 1 FROM document_chunks) THEN
            RAISE EXCEPTION
                'Refusing to change populated document_chunks from % to vector(384). Existing data was preserved; arrange explicit re-embedding first.',
                embedding_type;
        END IF;
        ALTER TABLE document_chunks
            ALTER COLUMN embedding TYPE VECTOR(384) USING embedding::VECTOR(384);
    END IF;
END $$;

ALTER TABLE messages ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::JSONB;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);

-- Legacy documents have NULL hashes and are preserved. New PDF ingestions use
-- SHA-256 hashes; PostgreSQL allows multiple NULLs in this unique index.
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_messages_session_order ON messages(session_id, created_at, id);
