"""Strict function schemas exposed to the planning model."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "search_web",
        "description": "Search the public web and return candidate page URLs. Results are not evidence until fetched.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A focused web search query."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "fetch_page",
        "description": "Fetch a URL returned by search_web, extract readable text, and register it as a source.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "An exact URL previously returned by search_web."},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "summarize_sources",
        "description": "Return short, exact evidence passages from one or more fetched sources for a focus topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fetched source IDs such as S1 and S2.",
                },
                "focus": {"type": "string", "description": "The facts or comparison to extract."},
            },
            "required": ["source_ids", "focus"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "submit_answer",
        "description": "Submit the final answer as atomic claims linked to exact quotations from fetched sources.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "evidence": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "source_id": {"type": "string"},
                                        "quote": {
                                            "type": "string",
                                            "description": "An exact passage copied from the fetched source text.",
                                        },
                                    },
                                    "required": ["source_id", "quote"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["text", "evidence"],
                        "additionalProperties": False,
                    },
                },
                "limitations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Operational research limitations; use an empty array when there are none.",
                },
            },
            "required": ["title", "claims", "limitations"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]
