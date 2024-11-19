# Financial Document RAG System

A Retrieval-Augmented Generation (RAG) system for processing and querying financial documents, built with FastAPI and Qdrant.

## Quick Start

### Local Development

1. Install dependencies:
```bash
poetry install
```
2. Start Qdrant:
```bash
docker run -d \ 
  -p 6333:6333 \ 
  -p 6334:6334 \ 
  -v qdrant_storage:/qdrant/storage \ 
  -e QDRANT_ALLOW_RECOVERY_MODE=true \ 
  qdrant/qdrant:latest
```

or using docker compose:
```bash
docker-compose up --build
```
3. Copy `.env.example` to `.env` and fill in the required secrets:
`OPENAI_API_KEY`

2. Run the server:
```bash
poetry run uvicorn app.main:app --reload
```

## API Endpoints

This application exposes three endpoints:
- `/api/ingest` - Ingest a list of financial documents into the vector database.
- `/api/chat` - OpenAI-like chat endpoint for querying the vector database, allows to use custom UI.

## D&D AKA Design and Decisions

This is a very simple RAG system, that specializes in documents with pre-defined structure.

Ingest endpoint accepts JSON object with list of documents.
First, the document list is split into separate objects and in order to speed up the process, they are batched in batches of 10. This number is arbitrary and can be configured. It has been chosen as a simple way to work around the OpenAI API RPM limitations.
Then, for each document, the following steps are performed:
1. Pre-text and post-text are extracted from the document and concatenated together as `context`.
2. Context from previous step is passed into prompt for table verbalization and table is converted into separate sentences, which .
3. Table is verbalized using GPT-4o-mini.
4. Pre-text, verbalized table and post-text are concatenated and split into chunks.
5. Each chunk is embedded using OpenAI API.