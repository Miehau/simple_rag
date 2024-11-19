from openai import AsyncOpenAI
import os
from typing import List, Optional
from .types import FinancialDocument
from .prompts import TABLE_SYSTEM_PROMPT, CHUNK_SYSTEM_PROMPT

class EmbeddingService:
    def __init__(self, api_key: Optional[str] = None):
        if not api_key and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OpenAI API key is required")
        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.MAX_CHUNK_SIZE = 8000

    async def verbalize_table(self, context: str, table: List[List[str]]) -> List[str]:
        table_str = "\n".join([",".join(str(cell) for cell in row) for row in table])
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": TABLE_SYSTEM_PROMPT},
                    {"role": "user", "content": 
                        f"""Context: {context}
                        Table:
                        {table_str}"""}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content.split("\n") or []
        except Exception as e:
            print(f"Table verbalization failed: {e}")
            return table_str

    async def create_chunks(self, data: str) -> List[str]:
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CHUNK_SYSTEM_PROMPT},
                {"role": "user", "content": data}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.split("\n") or []

    async def create_chunk(self, document: FinancialDocument) -> List[str]:
        # Prepare context for table verbalization
        pre_text = "\n".join(document.pre_text) if document.pre_text else ""
        post_text = "\n".join(document.post_text) if document.post_text else ""
        context = "\n".join(filter(None, [pre_text, post_text]))
        
        content_parts = []
        if pre_text:
            content_parts.append(pre_text)
        
        if document.table:
            table_text = await self.verbalize_table(context, document.table)
            content_parts.append(table_text)
            
        if post_text:
            content_parts.append(post_text)

        full_content = " ".join(content_parts)
        chunked_text = await self.create_chunks(full_content)
        return chunked_text

    async def embed(self, text: str) -> List[float]:
        response = await self.client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding

    async def chat_completion(self, messages: List[dict], temperature: float = 0.7) -> dict:
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=temperature
        )
        return {
            "id": response.id,
            "object": "chat.completion",
            "created": response.created,
            "model": response.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": response.choices[0].message.role,
                    "content": response.choices[0].message.content
                },
                "finish_reason": response.choices[0].finish_reason
            }],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        } 