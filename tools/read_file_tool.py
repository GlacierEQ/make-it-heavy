from .base_tool import BaseTool


class ReadFileTool(BaseTool):
    def __init__(self, config: dict):
        self.config = config

    @property
    def name(self):
        return "read_file"

    @property
    def description(self):
        return "Read a UTF-8 text file from the local runtime"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    def execute(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return {"success": True, "path": path, "content": handle.read()}
        except (OSError, UnicodeError) as exc:
            return {"success": False, "error": str(exc)}
