import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, mock_open, patch

from tools import supabase_logger


class SupabaseLoggerSecurityTests(unittest.TestCase):
    def test_case_scope_is_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "case_id is required"):
                supabase_logger._resolve_case_id(None)

    def test_explicit_case_scope_is_trimmed(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                supabase_logger._resolve_case_id("  case-test  "),
                "case-test",
            )

    def test_environment_case_scope_is_supported(self):
        with patch.dict(os.environ, {"APEX_CASE_ID": "case-env"}, clear=True):
            self.assertEqual(supabase_logger._resolve_case_id(None), "case-env")

    def test_missing_scope_fails_before_remote_or_local_write(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "tools.supabase_logger.get_supabase_client"
        ) as get_client, patch("builtins.open") as open_file:
            with self.assertRaises(ValueError):
                supabase_logger.log_apex_run(
                    query="query",
                    sub_questions=[],
                    agent_responses=[],
                    synthesis="synthesis",
                )

        get_client.assert_not_called()
        open_file.assert_not_called()

    def test_remote_error_detail_is_not_printed_before_local_fallback(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = RuntimeError(
            "sensitive provider detail"
        )
        opened = mock_open()
        output = io.StringIO()

        with patch.dict(os.environ, {}, clear=True), patch(
            "tools.supabase_logger.get_supabase_client", return_value=client
        ), patch("builtins.open", opened), redirect_stdout(output):
            record = supabase_logger.log_apex_run(
                query="query",
                sub_questions=["one"],
                agent_responses=[{"answer": "two"}],
                synthesis="synthesis",
                case_id="case-test",
            )

        rendered = output.getvalue()
        self.assertNotIn("sensitive provider detail", rendered)
        self.assertIn("RuntimeError", rendered)
        self.assertEqual(record["case_id"], "case-test")
        opened.assert_called_once_with("apex_runs.jsonl", "a", encoding="utf-8")
        written = "".join(
            call.args[0]
            for call in opened().write.call_args_list
            if call.args
        )
        self.assertIn('"case_id": "case-test"', written)


if __name__ == "__main__":
    unittest.main()
