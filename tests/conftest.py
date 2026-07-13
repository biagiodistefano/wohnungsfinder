from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def search_html() -> str:
    return (FIXTURES / "willhaben_search.html").read_text(encoding="utf-8")


@pytest.fixture
def detail_html() -> str:
    return (FIXTURES / "willhaben_detail.html").read_text(encoding="utf-8")
