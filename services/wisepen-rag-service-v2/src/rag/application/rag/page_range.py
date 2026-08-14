"""把内部有序 page labels 投影为统一的模型可见页范围。"""

from collections.abc import Sequence


def format_page_range(page_labels: Sequence[str]) -> str | None:
    labels = list(dict.fromkeys(page_labels))
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]
    return f"{labels[0]} - {labels[-1]}"
