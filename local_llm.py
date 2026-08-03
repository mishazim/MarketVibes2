"""Local LLM inference via Ollama — replaces the Anthropic client.

Runs entirely on-machine with no API key and no per-token cost. Both the news
sweep's classification pass (news_sentiment.py) and the final contrarian
synthesis (analysis.py) call chat_json() with a prompt asking for one JSON
object back.
"""

import json
import re
import time

import ollama

import config

_client = ollama.Client(host=config.OLLAMA_HOST)


def _extract_json(raw: str) -> dict | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def chat_json(prompt: str, max_tokens: int = 2048) -> dict | None:
    """Call the local model and return its parsed JSON reply, or None on failure.

    Retries only on connection errors (Ollama's background service still
    starting up) — there's no rate limit to back off from since this is local.
    """
    delay = 3
    for attempt in range(3):
        try:
            response = _client.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"num_predict": max_tokens},
            )
            return _extract_json(response["message"]["content"])
        except ollama.ResponseError as exc:
            print(f"    Ollama error: {exc}. Has `ollama pull {config.OLLAMA_MODEL}` "
                  f"been run?")
            return None
        except ConnectionError as exc:
            if attempt == 2:
                print(f"    Could not reach Ollama at {config.OLLAMA_HOST} ({exc}). "
                      f"Is the Ollama app/service running?")
                return None
            print(f"    Ollama not reachable yet — retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2
    return None


if __name__ == "__main__":
    result = chat_json(
        'Reply with ONLY this exact JSON object, no other text: '
        '{"ok": true, "model_check": "pass"}'
    )
    print(result)
