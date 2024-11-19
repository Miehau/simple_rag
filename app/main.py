from typing import List, Optional
from pydantic import BaseModel
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from qdrant_client import QdrantClient, models
from .ingestor import Ingestor
from .openai_service import EmbeddingService
from .types import FinancialDocument
from dotenv import load_dotenv
import os
import time
from fastapi.middleware.cors import CORSMiddleware
import logging 
from collections import defaultdict
import threading
from asyncio import gather, Semaphore  # Add this import

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Add CORS middleware
# This is added as my local server is running on a different port than the frontend
# On production this shouldn't be configured like this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

COLLECTION_NAME = "financial_docs2"

# Initialize Qdrant client
qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
qdrant_client = QdrantClient(url=qdrant_url)
try:
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "size": 1536,
            "distance": "Cosine"
        }
    )
except Exception:
    print("Collection might already exist")

ingestor = Ingestor(qdrant_client, COLLECTION_NAME)
embedder = EmbeddingService()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False


# Add this after other global variables
ingestion_progress = defaultdict(dict)
progress_lock = threading.Lock()


@app.post("/api/ingest")
async def ingest_document(documents: List[FinancialDocument]):
    try:
        batch_id = str(uuid.uuid4())
        total_documents = len(documents)
        semaphore = Semaphore(10) 
        
        # Initialize progress tracking for this batch
        with progress_lock:
            ingestion_progress[batch_id] = {
                "total": total_documents,
                "processed": 0,
                "status": "in_progress",
                "current_tasks": 0,
                "percent_complete": 0.0
            }
        
        logger.info(f"Starting ingestion of {total_documents} documents (Batch ID: {batch_id})")
        
        async def process_document(doc):
            async with semaphore:
                with progress_lock:
                    ingestion_progress[batch_id]["current_tasks"] += 1
                
                try:
                    await ingestor.ingest([doc])
                finally:
                    with progress_lock:
                        ingestion_progress[batch_id]["processed"] += 1
                        current_processed = ingestion_progress[batch_id]["processed"]
                        ingestion_progress[batch_id]["current_tasks"] -= 1
                        ingestion_progress[batch_id]["percent_complete"] = (
                            current_processed / total_documents
                        ) * 100
                        
                        # Log progress after each 10 documents
                        if current_processed % 10 == 0:
                            logger.info(
                                f"Batch {batch_id}: Processed {current_processed}/{total_documents} "
                                f"documents ({ingestion_progress[batch_id]['percent_complete']:.1f}%)"
                            )
        
        # Process all documents with max 10 concurrent tasks
        await gather(*[process_document(doc) for doc in documents])
        
        # Mark as complete
        with progress_lock:
            ingestion_progress[batch_id]["status"] = "completed"
            ingestion_progress[batch_id]["percent_complete"] = 100.0
            
        logger.info(f"Completed ingestion of all {total_documents} documents (Batch ID: {batch_id})")
        return {"batch_id": batch_id, "message": "Ingestion completed"}
    except Exception as e:
        with progress_lock:
            if batch_id in ingestion_progress:
                ingestion_progress[batch_id]["status"] = "failed"
                ingestion_progress[batch_id]["error"] = str(e)
        
        logger.error(f"Ingestion failed for batch {batch_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        start_time = time.time()
        logger.info("Processing chat request")
        
        # Generate a response using the last message as the query
        query = request.messages[-1].content
        logger.info(f"Query: {query[:100]}...")
        
        # Search in Qdrant for relevant context
        logger.info("Searching for relevant context...")
        # Vector search
        vector_results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=await embedder.embed(query),
            limit=10,
            score_threshold=0.6,
            with_payload=["text"]
        )

        # Get unique results based on text content
        search_result = list({r.payload["text"]: r for r in vector_results}.values())
        logger.info(f"Found {len(search_result)} relevant chunks")
        
        # Format the context from search results
        context = "\n".join(r.payload["text"] for r in search_result)
        
        # Get response from OpenAI
        logger.info("Requesting completion from OpenAI...")
        response = await embedder.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": f"""
                    You are a helpful assistant that answers questions based on the provided context.
                    Only use the information from the context to answer questions.
                    If you cannot find the answer in the context, say so.
                    <context>
                    {context}
                    </context>
                    """
                },
                *[{"role": msg.role, "content": msg.content} for msg in request.messages]
            ],
            temperature=request.temperature
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        logger.info(f"Chat request completed in {processing_time:.2f} seconds")
        
        return response

    except Exception as e:
        logger.error(f"Chat request failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 
