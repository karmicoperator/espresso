"""
Context7 Documentation Fetcher via Dedalus MCP Gateway.

Uses Dedalus as the MCP gateway to call Context7's documentation tools.
This fetches LIVE, up-to-date Manim documentation instead of relying on
static reference files that may become outdated.

Flow:
  1. Call Dedalus API (OpenAI-compatible) with Context7 MCP tools registered
  2. The LLM (cheap model) orchestrates calling Context7 to fetch docs
  3. Returns structured Manim documentation for the ManimGenerator

Sponsor Track: Dedalus "Best use of tool calling" 
  - Uses Dedalus SDK as MCP gateway
  - Context7 MCP for live documentation retrieval
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEDALUS_API_KEY = os.environ.get(
    "DEDALUS_API_KEY",
    "dsk-test-098830a9a4d7-edd901a3e4a640ec568d22ec8244902f",
)
DEDALUS_BASE_URL = "https://api.dedaluslabs.ai/v1"

# Context7 REST API (direct fallback)
CONTEXT7_API_BASE = "https://context7.com/api/v2"

# Manim library identifier on Context7
MANIM_LIBRARY_NAME = "manim"

# Cache for fetched docs to avoid redundant API calls within a pipeline run
_docs_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Context7 REST API helpers (direct calls)
# ---------------------------------------------------------------------------

async def _resolve_library_id(library_name: str) -> Optional[str]:
    """
    Resolve a library name to a Context7 library ID.
    
    Context7 MCP tool: resolve-library-id
    Uses the /api/v2/search endpoint.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{CONTEXT7_API_BASE}/search",
                params={"query": library_name},
            )
            resp.raise_for_status()
            data = resp.json()

            # Response is {"results": [{"id": "...", "title": "...", ...}, ...]}
            results = []
            if isinstance(data, dict):
                results = data.get("results", [])
            elif isinstance(data, list):
                results = data

            if results:
                # Prefer the community docs (most comprehensive)
                for r in results:
                    rid = r.get("id", "")
                    if "community" in rid.lower() or "stable" in rid.lower():
                        logger.info("Context7: Resolved '%s' -> %s (%s, %d tokens)",
                                    library_name, rid, r.get("title"), r.get("totalTokens", 0))
                        return rid
                # Fallback to first result
                rid = results[0].get("id", "")
                logger.info("Context7: Resolved '%s' -> %s", library_name, rid)
                return rid

            logger.warning("Context7: No library found for '%s'", library_name)
            return None
    except Exception as exc:
        logger.error("Context7 resolve-library-id failed: %s", exc)
        return None


async def _get_library_docs(
    library_id: str,
    query: str = "animations mobjects scenes",
    max_tokens: int = 5000,
) -> Optional[str]:
    """
    Fetch documentation for a library from Context7.
    
    Context7 MCP tool: get-library-docs
    Uses the /api/v2/context endpoint.
    Returns plain text documentation with code examples.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{CONTEXT7_API_BASE}/context",
                params={
                    "libraryId": library_id,
                    "query": query,
                    "tokens": str(max_tokens),
                },
            )
            resp.raise_for_status()

            # Context7 returns text/plain, not JSON
            content_type = resp.headers.get("content-type", "")
            if "text/plain" in content_type:
                return resp.text
            
            # Fallback: try JSON
            try:
                data = resp.json()
                if isinstance(data, dict):
                    return data.get("context") or data.get("content") or json.dumps(data, indent=2)
                return str(data)
            except Exception:
                return resp.text
    except Exception as exc:
        logger.error("Context7 get-library-docs failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Dedalus MCP Gateway integration
# ---------------------------------------------------------------------------

CONTEXT7_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "resolve_library_id",
            "description": (
                "Resolves a general library name to a Context7-compatible library ID. "
                "Call this FIRST before fetching documentation with get_library_docs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "libraryName": {
                        "type": "string",
                        "description": "Library name to search for (e.g., 'manim community', 'react', 'numpy')",
                    }
                },
                "required": ["libraryName"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_library_docs",
            "description": (
                "Fetches up-to-date documentation for a library from Context7. "
                "Returns real code examples and API references. "
                "You MUST call resolve_library_id first to get the libraryId."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "libraryId": {
                        "type": "string",
                        "description": "Context7 library ID obtained from resolve_library_id",
                    },
                    "query": {
                        "type": "string",
                        "description": "Specific topic or API to look up (e.g., 'animations Scene FadeIn', 'ThreeDScene camera', 'MathTex equations')",
                    },
                    "tokens": {
                        "type": "integer",
                        "description": "Max tokens of documentation to return (default 5000)",
                        "default": 5000,
                    },
                },
                "required": ["libraryId", "query"],
            },
        },
    },
]


async def _handle_tool_call(tool_name: str, arguments: dict) -> str:
    """Execute a Context7 tool call and return the result."""
    if tool_name == "resolve_library_id":
        library_name = arguments.get("libraryName", "manim community")
        lib_id = await _resolve_library_id(library_name)
        if lib_id:
            return json.dumps({"library_id": lib_id, "status": "resolved"})
        return json.dumps({"error": "Library not found", "library_name": library_name})

    elif tool_name == "get_library_docs":
        library_id = arguments.get("libraryId", "")
        query = arguments.get("query", "animations")
        tokens = arguments.get("tokens", 5000)
        docs = await _get_library_docs(library_id, query, tokens)
        return docs or json.dumps({"error": "Failed to fetch documentation"})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


async def fetch_manim_docs_via_dedalus(
    query: str = "animations mobjects Scene ThreeDScene",
    max_tokens: int = 5000,
) -> str:
    """
    Fetch live Manim documentation using Dedalus as the MCP gateway.
    
    This makes ONE cheap Dedalus API call (using a fast model) that
    orchestrates Context7 tool calls to retrieve up-to-date documentation.
    
    The fetched docs are then passed to the ManimGenerator which runs
    on Martian/Opus for the actual code generation.
    
    Hackathon Track: Dedalus "Best use of tool calling"
    
    Args:
        query: What aspect of Manim to look up
        max_tokens: Max documentation tokens to return
        
    Returns:
        Formatted documentation string, or empty string on failure
    """
    cache_key = f"manim:{query}:{max_tokens}"
    if cache_key in _docs_cache:
        logger.info("Context7 docs cache hit for query: %s", query)
        return _docs_cache[cache_key]

    logger.info("=" * 50)
    logger.info("DEDALUS + CONTEXT7: Fetching live Manim docs")
    logger.info("  Query: %s", query)
    logger.info("  Max tokens: %s", max_tokens)

    try:
        # Use OpenAI-compatible API pointed at Dedalus
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=DEDALUS_API_KEY,
            base_url=DEDALUS_BASE_URL,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a documentation retrieval assistant. "
                    "Use the provided tools to fetch current Manim library documentation. "
                    "First call resolve_library_id with 'manim community', "
                    "then call get_library_docs with the returned ID and the user's query. "
                    "Return ONLY the raw documentation text from the tool, no extra commentary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Fetch the latest Manim Community Edition documentation about: {query}. "
                    f"I need accurate, up-to-date API references for generating animation code."
                ),
            },
        ]

        # Step 1: Call Dedalus with tool definitions
        response = await client.chat.completions.create(
            model="anthropic/claude-3-5-haiku-latest",
            messages=messages,
            tools=CONTEXT7_TOOLS,
            tool_choice={"type": "auto"},
            max_tokens=1024,
        )

        msg = response.choices[0].message

        # Step 2: Handle tool calls (Dedalus orchestrates, we execute Context7)
        # We also capture the raw docs from get_library_docs directly,
        # since the cheap model may not repeat the full text.
        max_rounds = 4
        round_count = 0
        fetched_docs = ""

        while msg.tool_calls and round_count < max_rounds:
            round_count += 1
            messages.append(msg)  # Add assistant message with tool calls

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                logger.info("  Dedalus tool call [%d]: %s(%s)", round_count, fn_name, fn_args)

                # Execute the Context7 tool
                tool_result = await _handle_tool_call(fn_name, fn_args)

                # Capture the docs directly from get_library_docs
                if fn_name == "get_library_docs" and tool_result and not tool_result.startswith("{"):
                    fetched_docs = tool_result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

            # Continue the conversation with tool results
            response = await client.chat.completions.create(
                model="anthropic/claude-3-5-haiku-latest",
                messages=messages,
                tools=CONTEXT7_TOOLS,
                tool_choice={"type": "auto"},
                max_tokens=2048,
            )
            msg = response.choices[0].message

        # Use the LLM's final response if available, otherwise use the raw docs
        result_text = msg.content or ""
        if not result_text and fetched_docs:
            result_text = fetched_docs
            logger.info("  Using raw Context7 docs directly (LLM did not repeat them)")

        if result_text:
            logger.info("  ✓ Fetched %d chars of live Manim docs via Dedalus+Context7", len(result_text))
            _docs_cache[cache_key] = result_text
            return result_text
        else:
            logger.warning("  Dedalus returned empty response, falling back to direct Context7")
            return ""

    except Exception as exc:
        logger.error("  Dedalus + Context7 failed: %s", exc)
        logger.info("  Falling back to direct Context7 API")
        return ""


async def fetch_manim_docs_direct(
    query: str = "animations mobjects Scene ThreeDScene",
    max_tokens: int = 5000,
) -> str:
    """
    Direct Context7 API fallback (no Dedalus gateway).
    
    Used when Dedalus is unavailable or for testing Context7 independently.
    """
    cache_key = f"direct:manim:{query}:{max_tokens}"
    if cache_key in _docs_cache:
        return _docs_cache[cache_key]

    logger.info("Context7 direct: Fetching docs for query '%s'", query)

    # Step 1: Resolve library ID
    lib_id = await _resolve_library_id("manim community")
    if not lib_id:
        logger.warning("Context7: Could not resolve 'manim' library")
        return ""

    # Step 2: Fetch documentation
    docs = await _get_library_docs(lib_id, query, max_tokens)
    if docs:
        logger.info("Context7 direct: Fetched %d chars", len(docs))
        _docs_cache[cache_key] = docs
        return docs

    return ""


async def get_manim_docs(
    topic: str = "animations mobjects Scene ThreeDScene MathTex",
    max_tokens: int = 5000,
    use_dedalus: bool = True,
) -> str:
    """
    Main entry point: Fetch live Manim documentation.
    
    Tries Dedalus+Context7 first, falls back to direct Context7,
    then falls back to static docs if both fail.
    
    Args:
        topic: What Manim APIs/concepts to look up
        max_tokens: Max documentation tokens
        use_dedalus: Whether to try Dedalus gateway first
        
    Returns:
        Documentation string (live or static fallback)
    """
    docs = ""

    if use_dedalus and DEDALUS_API_KEY:
        docs = await fetch_manim_docs_via_dedalus(topic, max_tokens)

    if not docs:
        docs = await fetch_manim_docs_direct(topic, max_tokens)

    if not docs:
        logger.info("All live doc sources failed, using static manim_reference.md")
        static_path = Path(__file__).parent.parent / "prompts" / "system" / "manim_reference.md"
        if static_path.exists():
            docs = static_path.read_text()

    return docs


def clear_docs_cache():
    """Clear the documentation cache (useful between pipeline runs)."""
    _docs_cache.clear()


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async def _test():
        print("=" * 60)
        print("Testing Context7 Documentation Fetcher")
        print("=" * 60)

        # Test 1: Direct Context7 API
        print("\n--- Test 1: Direct Context7 API ---")
        docs = await fetch_manim_docs_direct("animations Scene Create FadeIn")
        if docs:
            print(f"✓ Got {len(docs)} chars of documentation")
            print(f"  Preview: {docs[:200]}...")
        else:
            print("✗ Direct API returned nothing")

        clear_docs_cache()

        # Test 2: Via Dedalus gateway
        print("\n--- Test 2: Dedalus + Context7 MCP Gateway ---")
        docs = await fetch_manim_docs_via_dedalus("animations Scene Create FadeIn MathTex")
        if docs:
            print(f"✓ Got {len(docs)} chars of documentation via Dedalus")
            print(f"  Preview: {docs[:200]}...")
        else:
            print("✗ Dedalus gateway returned nothing")

        clear_docs_cache()

        # Test 3: Full pipeline entry point
        print("\n--- Test 3: Full get_manim_docs() ---")
        docs = await get_manim_docs("ThreeDScene 3D animations camera")
        if docs:
            print(f"✓ Got {len(docs)} chars via full pipeline")
            print(f"  Preview: {docs[:200]}...")
        else:
            print("✗ All methods failed")

    asyncio.run(_test())
