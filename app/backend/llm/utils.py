from dotenv import load_dotenv
from app.backend.llm.llm_agents import llm_singleton
from app.backend.llm.schemas import BearingCodes
from app.backend.llm.prompt_templates import text_to_codes, codes_to_sizes

load_dotenv()


def get_bearings(raw_text: str) -> str:
    """
    It uses an LLM to identify bearing codes in the given raw text. Then, it does a web search to find the
    dimensions of these bearings.
    :param raw_text: string containing the raw text
    :return: bearings with their dimensions
    """
    structured_llm = llm_singleton.llm.with_structured_output(BearingCodes)
    # this chain extracts bearing codes from raw text
    extraction_chain = text_to_codes | structured_llm
    # after extraction, it looks in the web for dimensions of the bearings
    full_chain = (
            {"codes": extraction_chain}
            | codes_to_sizes
            | llm_singleton.llm_bearing_search
    )
    return full_chain.invoke({"text_input": raw_text})["messages"][-1].content
