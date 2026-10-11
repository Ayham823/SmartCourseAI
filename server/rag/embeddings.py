import numpy as np
from threading import Lock
from server.errors import AppError


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model = None
_model_lock = Lock()


def get_embedding_model():
    global _model

    if _model is None:
        with _model_lock:
            if _model is None:
                # Loading torch/transformers belongs to the first RAG request,
                # not Flask startup, health checks, or deterministic tools.
                try:
                    from sentence_transformers import SentenceTransformer
                    _model = SentenceTransformer(MODEL_NAME)
                except Exception:
                    raise AppError("The course embedding model is unavailable. Check its local cache and network connection.", "embedding_unavailable", 503) from None

    return _model


def embed_text(text):
    model = get_embedding_model()

    embedding = model.encode(
        text,
        normalize_embeddings=True
    )

    return np.asarray(
        embedding,
        dtype=np.float32
    )


def embed_texts(texts):
    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        normalize_embeddings=True
    )

    return [
        np.asarray(
            embedding,
            dtype=np.float32
        )
        for embedding in embeddings
    ]
