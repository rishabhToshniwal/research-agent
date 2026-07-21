import proxy_patch
import os
import asyncio
from agents import Agent, ModelSettings, Runner, function_tool, trace
from dotenv import load_dotenv
import requests
from pydantic import BaseModel, Field

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LANGRAPH_SEARCH_API_KEY = os.getenv("LANGRAPH_SEARCH_API_KEY")
LANGRAPH_SEARCH_URL = os.getenv(
    "LANGRAPH_WEB_SEARCH_URL", "https://api.langsearch.com/v1/web-search"
)

Freshness = str  # oneDay | oneWeek | oneMonth | oneYear | noLimit

require_tool = ModelSettings(tool_choice="required")


# Format LangSearch result pages into numbered blocks (title, URL, summary/snippet) for downstream agents.
def _format_langsearch_pages(pages: list) -> str:
    blocks = []
    for i, page in enumerate(pages, start=1):
        url = page.get("url") or page.get("displayUrl") or ""
        title = page.get("name") or page.get("displayUrl") or url or "Untitled"
        body = page.get("summary") or page.get("snippet") or ""
        blocks.append(f"[{i}] {title}\nURL: {url}\n{body.strip()}")
    return "\n\n---\n\n".join(blocks)


# Call the LangSearch Web Search API and return formatted result text (or a clear error string).
def search_web(
    query: str,
    *,
    count: int = 3,
    freshness: Freshness = "noLimit",
    summary: bool = True,
) -> str:
    """Call LangSearch Web Search API and return LLM-friendly result text."""
    if not LANGRAPH_SEARCH_API_KEY:
        return "Error: LANGRAPH_SEARCH_API_KEY is not set in .env"

    payload = {
        "query": query,
        "freshness": freshness,
        "summary": summary,
        "count": max(1, min(count, 10)),
    }
    headers = {
        "Authorization": f"Bearer {LANGRAPH_SEARCH_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            LANGRAPH_SEARCH_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
    except requests.HTTPError as e:
        detail = e.response.text if e.response is not None else str(e)
        return f"LangSearch HTTP error: {e.response.status_code if e.response else 'unknown'}\n{detail}"
    except requests.RequestException as e:
        return f"LangSearch request failed: {e}"

    if body.get("code") != 200:
        return f"LangSearch API error (code={body.get('code')}): {body.get('msg')}"

    data = body.get("data") or {}
    pages = (data.get("webPages") or {}).get("value") or []
    if not pages:
        return f"No web results found for query: {query!r}"

    header = f"Query: {(data.get('queryContext') or {}).get('originalQuery', query)}\nResults: {len(pages)}\n\n"
    return header + _format_langsearch_pages(pages)


@function_tool
def web_search(query: str, count: int = 2, freshness: Freshness = "noLimit") -> str:
    """Search the public web for up-to-date information on a topic.

    Use for facts, news, or research that may not be in the model's training data.
    freshness: oneDay, oneWeek, oneMonth, oneYear, or noLimit (default).
    count: number of results to return (default 2).
    """
    return search_web(query, count=count, freshness=freshness, summary=True)

search_instructions = """
You are a research assistant, given a search term, you search the web for that term and produce a concise summary of the results.
The summary should be 2 or 3 sentences and less than 200 words.
Capture the main points and reply with summary of the results.
You must use web_search tool to search the web.
"""

web_search_tool = [web_search]


web_search_agent = Agent(name="web_search_agent", instructions=search_instructions, tools=web_search_tool, model=OPENAI_MODEL,model_settings=require_tool)

planner_instructions = """
You are a planner assistant, given a query, you come up with a set of web searches to perform to best answer the query.
.Output 2 terms to query for the web_search tool to perform.
"""

# Structured Output for planner agent

class WebSearchItem(BaseModel):
    reason: str = Field(description="The reason why the search is being performed")
    query: str = Field(description="The search term to use for web search")

class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem] = Field(description="The list of web search to perform to best answer the query")

planner_agent = Agent(name="planner_agent", instructions=planner_instructions, model=OPENAI_MODEL, output_type=WebSearchPlan)


writer_instructions = """
You are a senior researcher assistant tasked with writing a cohesive research report, for a given query.
You will be provided with the original query and some research. Generate a comprehensive report based on
research and query.
The output should be mark down formatted detailed report with 2 pages and less than 1000 words
"""

class ReportData(BaseModel):
    short_summary: str = Field(description="A 2-3 lines summary of the research report")
    markdown_report: str = Field(description="The detailed report in markdown format")
    follow_up_questions: list[str] = Field(description="Suggested follow up questions to further research")

writer_agent = Agent(name="writer_agent", instructions=writer_instructions, model=OPENAI_MODEL, output_type=ReportData)

@function_tool
def print_report(subject:str,text_body:str,html_body:str):
    """Print the research report to the console and save it to a html file.
       Args:
         subject: The subject of the research report
         text_body: The text body of the research report
         html_body: The html body of the research report
    """
    print(f"Subject: {subject}")
    # print(f"Text Body: {text_body}")
    print(f"HTML Body: {html_body}")
    with open(f"{subject}.html", "w", encoding="utf-8") as f:
      f.write(html_body)
    return f"Research report printed to console for subject: {subject}"

print_report_tool = [print_report]

printer_instructions = """
You are a provided with a report. Use your tool to print the report to a well presented and structured html.
"""

printer_agent = Agent(name="printer_agent", instructions=printer_instructions, tools=print_report_tool, model=OPENAI_MODEL, model_settings=require_tool)


async def plan(query:str):
    print(f"Running planner agent for query: {query}")
    result = await Runner.run(planner_agent, query)
    searches = result.final_output.searches
    print(f"Will perform {len(searches)} searches")
    tasks = [search(item) for item in searches] # Create a list of coroutines
    results = await asyncio.gather(*tasks) # Run coroutines in parallel
    print("Finished searching")
    return results

async def search(item:WebSearchItem):
    print(f"Searching for: {item.query} \n Reason for searching: {item.reason}")
    result = await Runner.run(web_search_agent, item.query)
    return result.final_output

async def write(query:str, search_results:list[str]):
    print(f"Running writer agent for query: {query}")
    input_message = f"Original query: {query}\nSummarized search results: {search_results}"
    result = await Runner.run(writer_agent, input_message)
    print(f"Finished writing report")
    return result.final_output

async def print_report(report:ReportData):
    print(f"Running printer agent for report: {report.short_summary}")
    result = await Runner.run(printer_agent, report.markdown_report)
    print(f"Finished printing report")
    return result.final_output
        

## Main function to run the research agent

async def research(query:str):
    with trace("Research Agent"):
     searches = await plan(query)
     report = await write(query, searches)
     await print_report(report)
     print(f"Finished research agent for query: {query}")


if __name__ == "__main__":
    asyncio.run(research("Most popular AI agent framework of 2026?"))
