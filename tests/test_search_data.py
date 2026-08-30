"""Regression tests for paid web search — empty DuckDuckGo instant answers must not ship as success."""
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SRC))

EMPTY_INSTANT_ANSWER = {
    "AbstractText": "",
    "RelatedTopics": [],
    "Heading": "",
    "AbstractURL": "",
}


def _fresh_search_data():
    sys.modules.pop("search_data", None)
    return importlib.import_module("search_data")


def test_instant_answer_empty_falls_back_to_html():
    module = _fresh_search_data()
    fixture = (FIXTURES / "ddg_bitcoin_price.html").read_text()

    with patch.object(module, "EXA_API_KEY", None), patch.object(
        module, "_fetch_json", return_value=EMPTY_INSTANT_ANSWER
    ), patch.object(module, "_fetch_text", return_value=fixture):
        result = module.web_search("bitcoin price", num_results=3)

    assert result["query"] == "bitcoin price"
    assert result["engine"] == "duckduckgo_html"
    assert result["count"] > 0
    assert len(result["results"]) > 0
    first = result["results"][0]
    assert first["title"]
    assert first["url"].startswith("https://")
    assert first["snippet"]
    assert "timestamp" in result


def test_empty_instant_answer_and_html_raises_502():
    module = _fresh_search_data()

    with patch.object(module, "EXA_API_KEY", None), patch.object(
        module, "_fetch_json", return_value=EMPTY_INSTANT_ANSWER
    ), patch.object(module, "_fetch_text", return_value="<html><body></body></html>"):
        with pytest.raises(HTTPException) as exc:
            module.web_search("bitcoin price", num_results=5)

    assert exc.value.status_code == 502
    assert "no results" in exc.value.detail.lower()


def test_parse_ddg_html_fixture_shape():
    module = _fresh_search_data()
    fixture = (FIXTURES / "ddg_bitcoin_price.html").read_text()
    results = module._parse_ddg_html_results(fixture, num_results=5)

    assert len(results) >= 2
    for row in results:
        assert set(row.keys()) >= {"title", "url", "snippet"}
        assert row["title"]
        assert row["url"].startswith("https://")


def test_instant_answer_with_results_skips_html():
    module = _fresh_search_data()
    instant = {
        "AbstractText": "Bitcoin is a cryptocurrency.",
        "Heading": "Bitcoin",
        "AbstractURL": "https://en.wikipedia.org/wiki/Bitcoin",
        "AbstractSource": "Wikipedia",
        "RelatedTopics": [],
    }

    with patch.object(module, "EXA_API_KEY", None), patch.object(
        module, "_fetch_json", return_value=instant
    ), patch.object(module, "_fetch_text") as html_fetch:
        result = module.web_search("bitcoin", num_results=3)

    html_fetch.assert_not_called()
    assert result["engine"] == "duckduckgo"
    assert result["count"] == 1
    assert result["results"][0]["title"] == "Bitcoin"
