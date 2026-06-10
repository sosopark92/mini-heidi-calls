import time


def chat_with_retry(client, max_retries: int = 5, **kwargs):
    """Call client.chat.completions.create with exponential backoff on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            if "rate_limit" in type(e).__name__.lower() or "429" in str(e):
                wait = 5 * (attempt + 1)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("LLM call failed after max retries")
