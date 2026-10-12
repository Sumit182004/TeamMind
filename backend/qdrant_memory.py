
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models


load_dotenv(Path(__file__).resolve().parent / ".env")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

COLLECTION_NAME = "teammind_memories"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError(
        "Set QDRANT_URL and QDRANT_API_KEY in backend/.env"
    )

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)


def ensure_collection():
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=client.get_embedding_size(MODEL_NAME),
                distance=models.Distance.COSINE,
            ),
        )


def save_memory(text: str, metadata: dict) -> str:
    """Embed and save a decision memory in Qdrant."""
    memory_id = str(uuid.uuid4())

    client.upload_collection(
        collection_name=COLLECTION_NAME,
        vectors=[
            models.Document(
                text=text,
                model=MODEL_NAME,
            )
        ],
        payload=[
            {
                "document": text,
                **metadata,
            }
        ],
        ids=[memory_id],
    )

    return memory_id


def search_memories(query: str, limit: int = 3) -> list[dict]:
    """Find memories semantically related to a query."""
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=models.Document(
            text=query,
            model=MODEL_NAME,
        ),
        limit=limit,
        with_payload=True,
    ).points

    return [
        {
            "id": str(point.id),
            "score": point.score,
            "document": point.payload.get("document", ""),
            "metadata": {
                key: value
                for key, value in point.payload.items()
                if key != "document"
            },
        }
        for point in results
    ]
