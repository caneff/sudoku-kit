"""The solve guide printed through a real Chromium (#156).

`test_solve_guide_html.py` pins the print CSS by reading the stylesheet; these
tests print the page and read the PDF Chromium writes. The board is the
invented 4x4 `TOY`. Each key idea card gets a distinct flat colour so the
PDF's drawing commands say which page it landed on, and the page's clip
rectangle gives the margins. Chromium comes from the Playwright cache
(`playwright install chromium`); a missing build fails the run, never a skip.
"""

import re
import zlib

import pytest
from guide_helpers import TOY, make_record
from test_solve_guide_html import SIX, _fill, _guide, _key

from sudoku_kit import guide_html

A4_POINTS = (595.28, 841.89)
MARGIN_POINTS = 15 / 25.4 * 72
CARDS = 5
CLIP = re.compile(rb"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re\nW\* n")
FILL = re.compile(rb"([\d.]+) ([\d.]+) ([\d.]+) rg")


def _card_colour(k):
    return (k * 20, 0, 0)


def _guide_html():
    entries = [_key(k, k) for k in (1, 2, 3, 4)] + [_fill(5, 5), _key(6, 6)]
    return guide_html.guide_page(TOY, make_record(*SIX), _guide(*entries))


def _tint_cards(page):
    rules = "".join(
        f"section.key:nth-of-type({k}) {{ background: rgb{_card_colour(k)} !important }}"
        for k in range(1, CARDS + 1)
    )
    return page.replace("</head>", f"<style>{rules}</style></head>")


@pytest.fixture(scope="module")
def chromium():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def printed(chromium):
    page = chromium.new_page()
    page.set_content(_tint_cards(_guide_html()))
    pdf = page.pdf(prefer_css_page_size=True, print_background=True)
    flags = page.evaluate(
        "() => [...document.querySelectorAll('details')]"
        ".map(d => getComputedStyle(d).display)"
    )
    page.emulate_media(media="print")
    hidden = page.evaluate(
        "() => [...document.querySelectorAll('details')]"
        ".map(d => getComputedStyle(d).display)"
    )
    page.close()
    return pdf, flags, hidden


def _pages(pdf):
    """Each page's content stream, decompressed, in page order."""
    streams = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            streams.append(zlib.decompress(m.group(1)))
        except zlib.error:
            continue
    return [s for s in streams if CLIP.search(s)]


def _cards_on(stream):
    """The numbers of the tinted cards a page draws."""
    wanted = {_card_colour(k): k for k in range(1, CARDS + 1)}
    found = set()
    for m in FILL.finditer(stream):
        rgb = tuple(round(float(v) * 255) for v in m.groups())
        if rgb in wanted:
            found.add(wanted[rgb])
    return found


def test_the_guide_prints_on_an_a4_page_with_15mm_margins(printed):
    pdf, _, _ = printed
    box = [
        float(v)
        for v in re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", pdf).groups()
    ]
    assert box == pytest.approx(A4_POINTS, abs=0.5)
    for stream in _pages(pdf):
        # the clip is in 1/4-point units under the page's .24 scale
        x, y, width, height = (
            float(v) * 0.24 / 1 for v in CLIP.search(stream).groups()
        )
        assert x == pytest.approx(MARGIN_POINTS, abs=0.5)
        assert y == pytest.approx(MARGIN_POINTS, abs=0.5)
        assert width == pytest.approx(A4_POINTS[0] - 2 * MARGIN_POINTS, abs=0.5)
        assert height == pytest.approx(A4_POINTS[1] - 2 * MARGIN_POINTS, abs=0.5)


def test_two_cards_share_a_page_when_they_fit(printed):
    pages = _pages(printed[0])
    assert len(pages) >= 2
    assert max(len(_cards_on(p)) for p in pages) >= 2


def test_no_card_is_split_across_pages(printed):
    pages = [_cards_on(p) for p in _pages(printed[0])]
    assert set().union(*pages) == set(range(1, CARDS + 1))
    for k in range(1, CARDS + 1):
        assert sum(k in on for on in pages) == 1, f"card {k} is on several pages"


def test_collapsed_lists_show_on_screen_and_vanish_in_print(printed):
    _, on_screen, in_print = printed
    assert on_screen and set(on_screen) != {"none"}
    assert set(in_print) == {"none"}
