import random
import time

import groq


def chat_with_retry(client, max_retries: int = 5, **kwargs):
    """Call Groq Chat Completions with rate-limit backoff."""

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)

        except groq.RateLimitError as exc:
            last_error = exc

            # Prefer Groq's Retry-After response header when available.
            retry_after = None

            if getattr(exc, "response", None) is not None:
                retry_after = exc.response.headers.get("retry-after")

            if retry_after:
                wait_seconds = float(retry_after)
            else:
                wait_seconds = min(
                    (2**attempt) + random.random(),
                    30,
                )

            time.sleep(wait_seconds)

        except (groq.APIConnectionError, groq.InternalServerError) as exc:
            last_error = exc
            wait_seconds = min((2**attempt) + random.random(), 30)
            time.sleep(wait_seconds)

    raise RuntimeError(
        f"Groq API failed after {max_retries} attempts "
        f"({type(last_error).__name__})."
    ) from last_error