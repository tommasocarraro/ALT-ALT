import os
from langchain_core.tools import tool
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@tool
def web_search(query: str) -> str:
    """
    Uses OpenAI's hosted web_search tool to answer queries with fresh info.
    """
    resp = oai.responses.create(
        model="gpt-4.1-mini",
        tools=[{"type": "web_search"}],
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text",
                     "text": f"Search the web and answer: {query}. Be concise."}
                ],
            }
        ],
    )
    return resp.output_text or "No answer."