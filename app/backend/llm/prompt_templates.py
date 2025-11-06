from langchain_core.prompts import ChatPromptTemplate

# from raw text, teaches the LLM to extract standard bearing codes
text_to_codes = ChatPromptTemplate.from_template(
    "Take the following text, extract the codes of standard bearings, and return a list of the codes."
    "Hint: look for 2RS/2Z to identify bearing codes."
    "\n\n------ TEXT BEGIN HERE ------\n\n{text_input}"
)

# from bearing codes, teaches the LLM to look for bearing dimensions in the web
codes_to_sizes = ChatPromptTemplate.from_template(
    "Perform a web search to find the dimensions (inner diameter x outer diameter x width) of the following bearing codes:\n\n{codes}"
)