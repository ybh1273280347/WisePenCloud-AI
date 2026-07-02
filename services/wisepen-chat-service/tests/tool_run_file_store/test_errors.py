import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from chat.application.tools.common.tool_run_file_store.errors import (
    InvalidToolFileRefError,
    ToolFileNotFoundError,
    ToolFileUnreadableError,
    tool_file_error_reason,
)


def test_tool_file_error_reason_maps_known_store_errors() -> None:
    assert tool_file_error_reason(InvalidToolFileRefError()) == "invalid_file_ref"
    assert tool_file_error_reason(ToolFileNotFoundError()) == "file_ref_unavailable"
    assert tool_file_error_reason(ToolFileUnreadableError()) == "file_unreadable"


def test_tool_file_error_reason_uses_default_for_unknown_errors() -> None:
    assert tool_file_error_reason(RuntimeError("boom")) == "file_ref_unavailable"
    assert tool_file_error_reason(RuntimeError("boom"), default="parse_failed") == "parse_failed"
