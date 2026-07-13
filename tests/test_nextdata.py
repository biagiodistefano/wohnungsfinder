from wohnung.nextdata import extract_next_data


def test_extract_next_data_search(search_html):
    data = extract_next_data(search_html)
    ads = data["props"]["pageProps"]["searchResult"]["advertSummaryList"]["advertSummary"]
    assert len(ads) >= 1


def test_extract_next_data_missing_returns_none():
    assert extract_next_data("<html>no script here</html>") is None
