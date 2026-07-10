from chat.application.tools.common.file_reference_store.core.errors import (
    InvalidFileReferenceError,
    ReferencedFileNotFoundError,
    ReferencedFileUnreadableError,
    file_reference_error_reason,
)


def test_file_reference_errors_map_to_stable_reasons() -> None:
    assert file_reference_error_reason(InvalidFileReferenceError()) == "invalid_file_ref"
    assert file_reference_error_reason(ReferencedFileNotFoundError()) == "file_ref_unavailable"
    assert file_reference_error_reason(ReferencedFileUnreadableError()) == "file_unreadable"
    assert file_reference_error_reason(RuntimeError()) == "file_ref_unavailable"
