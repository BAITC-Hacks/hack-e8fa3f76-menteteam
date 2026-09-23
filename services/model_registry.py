"""Process-local, lazy model lifecycle management."""
from functools import lru_cache


@lru_cache(maxsize=2)
def get_gemma(model_id: str):
    from services.llm import _load_gemma
    return _load_gemma(model_id)
