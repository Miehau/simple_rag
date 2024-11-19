from typing import List, Optional
import uuid
import logging
from qdrant_client import QdrantClient
from .types import FinancialDocument
from .openai_service import EmbeddingService

class Ingestor:
    def __init__(self, client: QdrantClient, collection_name: str):
        self.client = client
        self.collection_name = collection_name
        self.embedder = EmbeddingService()
        self.logger = logging.getLogger(__name__)

    async def ingest(self, data: List[FinancialDocument]) -> None:
        try:
            if not data:
                raise ValueError("Empty document list")

            total = len(data)
            self.logger.info(f"Starting ingestion of {total} documents")

            for idx, document in enumerate(data, 1):
                if not document.id:
                    raise ValueError("Document missing ID")

                # Create text chunk and generate embedding
                chunk = await self.embedder.create_chunk(document)
                vectors = [await self.embedder.embed(c) for c in chunk if c.strip()]

                # Upsert to Qdrant
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=[{
                        "id": str(uuid.uuid4()),
                        "vector": vector,
                        "payload": {
                            **document.model_dump(),
                            "text": c
                        }
                    } for vector, c in zip(vectors, chunk) if c.strip()]
                )
                
                progress = (idx / total) * 100
                self.logger.info(f"Processed {idx}/{total} documents ({progress:.1f}%)")

            self.logger.info("Ingestion completed successfully")
        except Exception as e:
            self.logger.error(f"Ingestion failed: {str(e)}")
            raise ValueError(f"Ingestion failed: {str(e)}")

    async def search(self, query: str) -> List[FinancialDocument]:
        # TODO: Implement actual vector search
        return [] 