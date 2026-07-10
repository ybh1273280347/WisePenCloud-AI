from __future__ import annotations

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"

# 几乎不会误删
_BASE_PRUNE_XPATH = (
    "//script",
    "//style",
    "//noscript",
    "//template",
    "//svg",
    "//canvas",
    "//iframe",
)

# 已有策略选择，存在一定召回损失
_LAYOUT_PRUNE_XPATH = (
    "//header",
    "//nav",
    "//footer",
    "//aside",
    "//form",
    "//button",
)

# 由真实异常样例驱动增加
_OBSERVED_NOISE_XPATH = (
    f"//*[translate(@aria-hidden, '{_UPPER}', '{_LOWER}')='true']",
    "//*[@hidden]",
    "//*[@inert]",
    "//*[@data-animated-cell]",
)

_PRUNE_XPATH = (
    *_BASE_PRUNE_XPATH,
    *_LAYOUT_PRUNE_XPATH,
    *_OBSERVED_NOISE_XPATH,
)


def build_prune_xpath(url: str | None = None) -> list[str]:
    return list(_PRUNE_XPATH)