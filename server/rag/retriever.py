from server.database.db import get_connection
from server.errors import AppError
from server.rag.embeddings import embed_text


def retrieve_chunks(
    query,
    limit=5
):
    if not isinstance(query, str) or not query.strip():
        raise AppError("Query cannot be empty.", "INVALID_QUERY", 400)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise AppError("Search limit must be between 1 and 100.", "INVALID_LIMIT", 400)

    query_embedding = embed_text(
        query
    )

    with get_connection() as conn:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    dc.id,
                    dc.content,
                    dc.page_number,
                    d.filename,

                    1 - (
                        dc.embedding
                        <=>
                        %s
                    ) AS similarity

                FROM document_chunks dc

                JOIN documents d
                    ON d.id =
                       dc.document_id

                WHERE dc.embedding
                    IS NOT NULL

                ORDER BY
                    dc.embedding
                    <=>
                    %s

                LIMIT %s;
                """,
                (
                    query_embedding,
                    query_embedding,
                    limit
                )
            )

            rows = cursor.fetchall()

    if not rows:
        raise AppError(
            "No course material is indexed yet. Ingest a course PDF before searching.",
            "NO_RELEVANT_EVIDENCE",
            422,
        )

    return [
        {
            "chunk_id": row[0],
            "content": row[1],
            "page_number": row[2],
            "source": row[3],
            "similarity": float(
                row[4]
            )
        }
        for row in rows
    ]
