from __future__ import annotations

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_LOWER_NAME = f"translate(name(), '{_UPPER}', '{_LOWER}')"

COMMON_TAG_PRUNE_XPATH: tuple[str, ...] = (
    "//script",
    "//style",
    "//noscript",
    "//template",
    "//svg",
    "//canvas",
    "//iframe",
    "//header",
    "//nav",
    "//footer",
    "//aside",
    "//form",
    "//button",
)

DOM_HYGIENE_PRUNE_XPATH: tuple[str, ...] = (
    f"//*[translate(@aria-hidden, '{_UPPER}', '{_LOWER}')='true']",
    "//*[@hidden]",
    "//*[@inert]",
    "//*[@data-animated-cell]",
)

PRESENTATIONAL_DATA_ATTR_MARKERS: tuple[str, ...] = (
    "animated",
    "animation",
    "ascii",
    "backdrop",
    "confetti",
    "decorative",
    "decoration",
    "motion",
    "ornament",
    "particle",
    "particles",
    "sparkle",
)


def build_prune_xpath(url: str | None = None) -> list[str]:
    rules: list[str] = []
    rules.extend(COMMON_TAG_PRUNE_XPATH)
    rules.extend(DOM_HYGIENE_PRUNE_XPATH)
    rules.extend(_build_presentational_data_attr_xpath())

    return _dedupe_preserve_order(rules)


def _build_presentational_data_attr_xpath() -> tuple[str, ...]:
    return tuple(
        f"//*[@*[{_is_presentational_data_attr(marker)}]]"
        for marker in PRESENTATIONAL_DATA_ATTR_MARKERS
    )


def _is_presentational_data_attr(marker: str) -> str:
    return f"starts-with({_LOWER_NAME}, 'data-') and contains({_LOWER_NAME}, '{marker}')"


def _dedupe_preserve_order(rules: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for rule in rules:
        if rule in seen:
            continue
        seen.add(rule)
        deduped.append(rule)
    return deduped
