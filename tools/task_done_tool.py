from datetime import datetime, timezone

from .base_tool import BaseTool


class TaskDoneTool(BaseTool):
    def __init__(self, config: dict):
        self.config = config

    @property
    def name(self):
        return "mark_task_complete"

    @property
    def description(self):
        return "Stop the model loop; completion remains pending human review"

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "task_summary": {"type": "string"},
                "completion_message": {"type": "string"},
            },
            "required": ["task_summary", "completion_message"],
        }

    def execute(self, task_summary: str, completion_message: str):
        return {
            "status": "pending_review",
            "result_classification": "model_inference",
            "task_summary": task_summary,
            "completion_message": completion_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
