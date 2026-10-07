"""Thin wrapper around the Claude API: one place for the model, its settings and the two call shapes we use."""
from typing import List, Type, TypeVar

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
# reading a diagram wrongly means shipping the wrong tool, so spend the effort
EFFORT = "high"
# if the model declines a request, the API re-runs it on a fallback model inside the same call
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# a web research turn can pause when the server-side tool loop reaches its limit; resume at most this many times
MAX_CONTINUATIONS = 5

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
]

T = TypeVar("T", bound=BaseModel)

# reads ANTHROPIC_API_KEY from the environment (or .env)
client = anthropic.Anthropic()


# tokens used since the process started; USD per million tokens for MODEL, to turn them into a cost
USAGE = {"input_tokens": 0, "output_tokens": 0, "requests": 0}
PRICE_PER_MTOK = {"input_tokens": 4.00, "output_tokens": 20.00}


def estimated_cost() -> float:
    """Rough cost in USD of the requests made so far. Cached input and web search fees are not counted apart."""
    return sum(USAGE[k] * PRICE_PER_MTOK[k] for k in PRICE_PER_MTOK) / 1_000_000


class LLMError(RuntimeError):
    pass


def _check(response) -> None:
    USAGE["requests"] += 1
    USAGE["input_tokens"] += response.usage.input_tokens
    USAGE["output_tokens"] += response.usage.output_tokens
    if response.stop_reason == "refusal":
        raise LLMError("The model declined this request.")
    if response.stop_reason == "max_tokens":
        raise LLMError("The model's answer was cut off before it finished.")


def ask_structured(content: List[dict], schema: Type[T], system: str) -> T:
    """One request whose answer is validated against `schema`."""
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
        output_config={"effort": EFFORT},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    _check(response)
    if response.parsed_output is None:
        raise LLMError("The model's answer did not match the expected format.")
    return response.parsed_output


def research(prompt: str, system: str) -> str:
    """One request in which the model may search the web and open pages. Returns its written findings."""
    messages = [{"role": "user", "content": prompt}]
    for _ in range(MAX_CONTINUATIONS + 1):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=WEB_TOOLS,
            output_config={"effort": EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        _check(response)
        if response.stop_reason != "pause_turn":
            return "\n".join(b.text for b in response.content if b.type == "text")
        # the server resumes where it stopped when the paused turn is sent back as is
        messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": response.content}]
    raise LLMError("Web research did not finish.")
