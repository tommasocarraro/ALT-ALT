import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from app.backend.llm.schemas import Bearings
from app.backend.llm.tools import web_search
load_dotenv()


class LLMSingleton:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
        self.llm_bearing_search = create_agent(
            model=self.llm,
            tools=[web_search],
            system_prompt="You are a helpful assistant that can search bearing information in the web.",
            response_format=Bearings
        )


llm_singleton = LLMSingleton()