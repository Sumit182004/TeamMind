
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

load_dotenv(Path(__file__).resolve().parent / ".env")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

COLLECTION_NAME = "teammind_memories"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
VECTOR_SIZE = 384

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("Set QDRANT_URL and QDRANT_API_KEY in environment variables.")

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

# Generate embeddings locally in the backend.
embedder = TextEmbedding(model_name=MODEL_NAME)


def embed_text(text: str) -> list[float]:
    return next(iter(embedder.embed([text]))).tolist()


def ensure_collection():
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE,
            ),
        )


def save_memory(text: str, metadata: dict) -> str:
    """Generate an embedding and save a memory in Qdrant Cloud."""
    ensure_collection()

    memory_id = str(uuid.uuid4())
    vector = embed_text(text)

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=memory_id,
                vector=vector,
                payload={
                    "document": text,
                    **metadata,
                },
            )
        ],
        wait=True,
    )

    return memory_id


def search_memories(query: str, limit: int = 3) -> list[dict]:
    """Retrieve semantically similar memories from Qdrant."""
    ensure_collection()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=embed_text(query),
        limit=limit,
        with_payload=True,
    ).points

    return [
        {
            "id": str(point.id),
            "score": point.score,
            "document": (point.payload or {}).get("document", ""),
            "metadata": {
                key: value
                for key, value in (point.payload or {}).items()
                if key != "document"
            },
        }
        for point in results
    ]
