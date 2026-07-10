from __future__ import annotations

import sys
import types
from pathlib import Path

from lxml import html as lxml_html

SERVICE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(SERVICE_ROOT.parent / "wisepen-common" / "src"))

logger_module = types.ModuleType("common.logger")
logger_module.warn = lambda *args, **kwargs: None
logger_module.info = lambda *args, **kwargs: None
logger_module.error = lambda *args, **kwargs: None
sys.modules["common.logger"] = logger_module

from chat.application.tools.web_tools.fetch_services.cleaners.html_prune_policy import (  # noqa: E402
    build_prune_xpath,
)
from chat.application.tools.web_tools.fetch_services.cleaners.trafilatura_cleaner import (  # noqa: E402
    TrafilaturaCleaner,
)


def test_build_prune_xpath_matches_ascii_backdrop_without_pruning_code_blocks() -> None:
    tree = lxml_html.fromstring(
        """
        <html>
          <body>
            <article id="article">
              <pre id="ascii-hero" class="SolAsciiHeroBackdrop-module__root__ascii" aria-hidden="true">5 6 .</pre>
              <div id="sol-ascii" data-sol-ascii-body>5 5 6</div>
              <span id="animated-cell" data-animated-cell="true">5</span>
              <main id="page-body" class="text-primary bg-background">
                Real article body
              </main>
              <pre id="code-sample" class="code-block terminal background">
                <code>for value in benchmark:</code>
              </pre>
              <table id="benchmark-table"><tr><td>p95</td><td>12 ms</td></tr></table>
              <pre id="log-output" class="terminal-output">INFO 200</pre>
            </article>
          </body>
        </html>
        """
    )

    matched_ids = _matched_element_ids(
        tree,
        build_prune_xpath(),
    )

    assert "ascii-hero" in matched_ids
    assert "sol-ascii" in matched_ids
    assert "animated-cell" in matched_ids
    assert "page-body" not in matched_ids
    assert "code-sample" not in matched_ids
    assert "benchmark-table" not in matched_ids
    assert "log-output" not in matched_ids


def test_trafilatura_cleaner_passes_prune_xpath_by_default(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_extract(*_: object, **kwargs: object) -> str:
        calls.update(kwargs)
        return "Title\n\n\nBody"

    monkeypatch.setattr(
        "chat.application.tools.web_tools.fetch_services.cleaners.trafilatura_cleaner.trafilatura.extract",
        fake_extract,
    )

    result = TrafilaturaCleaner().clean(
        "<html><body><main>Body</main></body></html>",
        url="https://openai.com/research/example",
    )

    assert result.markdown == "Title\n\nBody"
    assert calls["prune_xpath"] == build_prune_xpath()


def test_trafilatura_cleaner_can_disable_dom_prune(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_extract(*_: object, **kwargs: object) -> str:
        calls.update(kwargs)
        return "Body"

    monkeypatch.setattr(
        "chat.application.tools.web_tools.fetch_services.cleaners.trafilatura_cleaner.trafilatura.extract",
        fake_extract,
    )

    result = TrafilaturaCleaner(enable_dom_prune=False).clean(
        "<html><body><main>Body</main></body></html>",
        url="https://example.com/page",
    )

    assert result.markdown == "Body"
    assert calls["prune_xpath"] is None


def _matched_element_ids(tree, rules: list[str]) -> set[str]:
    matched_ids: set[str] = set()
    for rule in rules:
        for node in tree.xpath(rule):
            node_id = node.get("id")
            if node_id:
                matched_ids.add(node_id)
    return matched_ids
