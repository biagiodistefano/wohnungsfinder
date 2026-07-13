from wohnung.sources.willhaben import parse_detail, parse_search


def test_parse_search_returns_listings(search_html):
    listings = parse_search(search_html)
    assert listings
    l = listings[0]
    assert l.id.startswith("willhaben_")
    assert l.source == "willhaben"
    assert l.url.startswith("https://www.willhaben.at/iad/")
    assert l.size_m2 and l.size_m2 > 0
    assert l.rooms and l.rooms > 0
    assert l.postcode and 1000 <= l.postcode <= 1239
    assert l.district == int(str(l.postcode)[1:3])
    assert l.coordinates and len(l.coordinates) == 2
    assert l.image_urls and l.image_urls[0].startswith(IMG := "https://cache.willhaben.at/mmo/")


def test_parse_detail_enriches(detail_html):
    l = parse_detail(detail_html, base_id="willhaben_1701688262")
    assert l.description
    assert l.has_elevator in (True, False, None)
    assert l.has_outdoor in (True, False, None)
