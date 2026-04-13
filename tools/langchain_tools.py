import json
import asyncio
from typing import Optional, List, Dict
from langchain_core.tools import tool
from duckduckgo_search import DDGS
import aiohttp

@tool
def search_duckduckgo(query: str, max_results: int = 5) -> str:
    """
    Search DuckDuckGo for a given query and return the top results.
    Useful for finding current information, news, or factual answers.
    
    Args:
        query: The search string
        max_results: The maximum number of results to return (default: 5)
    """
    try:
        ddgs = DDGS()
        results = []
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "link": r.get("href", "")
            })
        if not results:
            return "No results found."
            
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error executing search: {str(e)}"

@tool
def search_serper(query: str, max_results: int = 5) -> str:
    """
    Search Google using the Serper API. 
    Requires SERPER_API_KEY environment variable to be set.
    
    Args:
        query: The search string
        max_results: The maximum number of results to return (default: 5)
    """
    import os
    import requests
    
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return "Error: SERPER_API_KEY environment variable not set. Please use DuckDuckGo search instead."
        
    url = "https://google.serper.dev/search"
    payload = json.dumps({
      "q": query,
      "num": max_results
    })
    headers = {
      'X-API-KEY': api_key,
      'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()
        data = response.json()
        
        results = []
        if "answer_box" in data:
            results.append({"type": "answer_box", "content": data["answer_box"]})
            
        if "organic" in data:
            for item in data["organic"][:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link": item.get("link", "")
                })
                
        if not results:
            return "No results found."
            
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error executing Serper search: {str(e)}"

@tool
def scrape_web_page(url: str) -> str:
    """
    Scrape the text content of a web page using Playwright.
    This runs a headless Chromium browser to render JavaScript and extracts the innerText of the body.
    
    Args:
        url: The full URL to scrape
    """
    import asyncio
    from playwright.async_api import async_playwright
    
    async def _do_scrape():
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    # Small wait to allow lazy loading
                    await page.wait_for_timeout(1000)
                    text = await page.evaluate("() => document.body.innerText")
                    return text
                finally:
                    await browser.close()
        except Exception as e:
            return f"Error scraping {url}: {str(e)}"

    # If already inside an running event loop (e.g. FastAPI/LangGraph), we must use nest_asyncio or standard await.
    # We will try to get the running loop. If it fails, run via asyncio.run
    try:
        loop = asyncio.get_running_loop()
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(_do_scrape())
    except RuntimeError:
        return asyncio.run(_do_scrape())

