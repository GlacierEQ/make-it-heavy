from .base_tool import BaseTool


class SearchTool(BaseTool):
    def __init__(self, config: dict):
        self.config = config

    @property
    def name(self):
        return "search_web"

    @property
    def description(self):
        return "Search the public web; returned material is unverified source data"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        }

    def execute(self, query: str, max_results: int = 5):
        from ddgs import DDGS

        bounded = max(1, min(int(max_results), 10))
        try:
            results = DDGS().text(query, max_results=bounded)
            return [
                {
                    "title": item.get("title"),
                    "url": item.get("href"),
                    "snippet": item.get("body"),
                    "verification_status": "unverified_source",
                }
                for item in results
            ]
        except Exception as exc:
            return [{"error": f"Search failed: {exc}"}]
