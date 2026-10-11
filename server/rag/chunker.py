def chunk_text(
    text,
    chunk_size=1200,
    overlap=200
):
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Require chunk_size > 0 and 0 <= overlap < chunk_size.")
    if not text:
        return []

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = end - overlap

    return chunks


def chunk_pages(
    pages,
    chunk_size=1200,
    overlap=200
):
    result = []

    chunk_index = 0

    for page in pages:

        page_chunks = chunk_text(
            page["text"],
            chunk_size=chunk_size,
            overlap=overlap
        )

        for chunk in page_chunks:

            result.append({
                "chunk_index": chunk_index,
                "page_number": page["page_number"],
                "content": chunk
            })

            chunk_index += 1

    return result
