
from qdrant_memory import (
    COLLECTION_NAME,
    client,
    ensure_collection,
    save_memory,
    search_memories,
)


def main():
    print("Connecting to Qdrant...")
    ensure_collection()
    print(f"Collection ready: {COLLECTION_NAME}")

    memory_id = save_memory(
        text=(
            "For a small development team, using an established "
            "authentication provider may reduce maintenance work, "
            "but introduce vendor dependency and recurring costs."
        ),
        metadata={
            "memory_type": "decision_lesson",
            "topic": "authentication",
            "source": "test",
        },
    )

    print(f"Saved memory: {memory_id}")

    results = search_memories(
        "What are the trade-offs of using an external authentication service?"
    )

    print("\nSearch results:")
    for result in results:
        print(result)

    print("\nQdrant test completed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        client.close()
