# app/llm/groq_synthesis.py

import logging
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger("groq-synthesis")

client = AsyncOpenAI(
    base_url=settings.GROQ_BASE_URL,
    api_key=settings.GROQ_API_KEY,
)

MODEL_NAME = settings.MODEL_NAME


async def run_groq(prompt: str) -> str:
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2048,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq synthesis failed: {e}")
        return "Sorry, I couldn't generate a response at this time."
