"""File mutation tool with a mandatory, default-off policy gate."""

import os
import tempfile

from .base_tool import BaseTool


class WriteFileTool(BaseTool):
    def __init__(self, config: dict):
        self.config = config

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write a UTF-8 file only when the operator has explicitly enabled "
            "tools.mutation_enabled. External actions are never performed."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "UTF-8 content"},
            },
            "required": ["path", "content"],
        }

    def execute(self, path: str, content: str) -> dict:
        if self.config.get("tools", {}).get("mutation_enabled") is not True:
            return {
                "success": False,
                "error": "write_file denied: tools.mutation_enabled is not explicitly true",
            }

        abs_path = os.path.abspath(path)
        parent = os.path.dirname(abs_path) or "."
        os.makedirs(parent, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=parent, delete=False
            ) as handle:
                temp_path = handle.name
                handle.write(content)
            os.replace(temp_path, abs_path)
            return {
                "success": True,
                "path": abs_path,
                "bytes_written": len(content.encode("utf-8")),
            }
        except (OSError, PermissionError) as exc:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return {"success": False, "error": f"write_file failed: {exc}"}
