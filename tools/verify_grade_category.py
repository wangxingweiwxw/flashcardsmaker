"""Verify the reviewed PDF classification locally or against --url production."""
import argparse
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading

from import_word_memory import ROOT, normalize_term
from validate_kdf import validate

GRADE = "grade-5-upper"


def verify_data():
    deck = json.loads((ROOT / "decks/word-memory-v2/deck.json").read_text(encoding="utf-8"))
    syllabus = json.loads((ROOT / "tools/data/grade-5-upper.json").read_text(encoding="utf-8"))
    assert len(syllabus["entries"]) == 113
    terms = {normalize_term(entry["term"]) for entry in syllabus["entries"]}
    expected = [card["id"] for card in deck["cards"] if normalize_term(card["front"]["primary"]) in terms]
    actual = [card["id"] for card in deck["cards"] if GRADE in card.get("categoryIds", [])]
    assert expected == actual and len(actual) == 54
    assert len(deck["cards"]) == 3980
    assert len(deck["categories"]) == 27
    assert normalize_term("Excellent!") == "excellent"
    assert normalize_term("giraﬀe") == "giraffe"
    assert normalize_term("take photos") != "photos"
    assert normalize_term("gardening") != "garden"
    # Reject invalid imported membership data consistently instead of silently filtering it.
    for memberships in ["letter-a", ["missing"], ["letter-a", "letter-a"], [{}], None]:
        invalid = deepcopy(deck)
        invalid["cards"][0]["categoryIds"] = memberships
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            errors, _ = validate(path)
            assert any("categoryIds" in error for error in errors), memberships
    print("PASS: 113 reviewed terms, 54 exact existing-card matches, no new cards, invalid memberships rejected", flush=True)
    return deck, expected


def verify_browser(url, deck, expected):
    from playwright.sync_api import sync_playwright

    def wait_render(page, count):
        page.wait_for_function("n => document.querySelector('#deck').getAttribute('aria-busy') === 'false' && document.querySelectorAll('.card').length === n", arg=count)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for width, height in [(1280, 900), (390, 844)]:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            errors, media = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: media.append(request.url) if ".mp3" in request.url else None)
            page.goto(url.rstrip("/") + "/?deck=word-memory-v2")
            wait_render(page, 3980)
            assert page.evaluate("app.deckData.deck.version") == "2.0.2"
            if width == 390:
                page.locator("#settingsToggle").click()
            assert page.locator("#filterCategory option").nth(1).get_attribute("value") == GRADE
            page.locator(f"[data-category='{GRADE}']").click()
            wait_render(page, 54)
            assert page.locator(".card").evaluate_all("cards => cards.map(c => c.dataset.cardId)") == expected
            assert not media, "Category selection must not preload audio"
            page.reload()
            wait_render(page, 54)
            assert page.locator("#filterCategory").input_value() == GRADE
            if width == 390 and not page.locator("#filterCategory").is_visible():
                page.locator("#settingsToggle").click()
            # The same action card and its progress appear in both overlapping categories.
            page.fill("#search", "行动如神")
            wait_render(page, 1)
            action_id = page.locator(".card").get_attribute("data-card-id")
            page.locator(".front .term").click()
            page.locator("[data-status=known]").click()
            page.select_option("#filterCategory", "letter-a")
            wait_render(page, 1)
            assert page.locator(".card").get_attribute("data-card-id") == action_id
            assert page.evaluate("id => cardState(id).status", action_id) == "known"
            page.select_option("#filterCategory", GRADE)
            page.fill("#search", "")
            page.select_option("#filterStatus", "known")
            wait_render(page, 1)
            assert page.locator(".card").get_attribute("data-card-id") == action_id
            page.select_option("#filterStatus", "all")
            wait_render(page, 54)
            page.locator(".front .audio-button").first.click()
            page.wait_for_function("activePronunciation && activePronunciation.audio.currentTime > 0")
            page.wait_for_function("activePronunciation === null")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(ROOT / f"outputs/grade-5-upper-{width}.png"))
            # Every existing alphabet category still includes all its original cards.
            for category in deck["categories"]:
                if not category["id"].startswith("letter-"):
                    continue
                ids = [c["id"] for c in deck["cards"] if c["categoryId"] == category["id"]]
                page.select_option("#filterCategory", category["id"])
                wait_render(page, len(ids))
                assert page.locator(".card").evaluate_all("cards => cards.map(c => c.dataset.cardId)") == ids
            page.select_option("#filterCategory", "all")
            wait_render(page, 3980)
            assert page.locator("#loadMore").count() == 0
            assert page.locator(".card").nth(100).locator(".front .term").inner_text() == "ankle"
            assert page.locator(".card").nth(101).locator(".front .term").inner_text() == "announce"
            for memberships in ["letter-a", ["missing"], ["letter-a", "letter-a"], [{}], None]:
                assert page.evaluate("ids => { const d = JSON.parse(JSON.stringify(app.deckData)); d.cards[0].categoryIds = ids; return !validateDeck(d).valid; }", memberships)
            assert not errors, errors
            context.close()
            print(f"PASS {width}px: category/filter persistence, shared progress, playback, all 26 letter categories and automatic loading", flush=True)
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url")
    args = parser.parse_args()
    deck, expected = verify_data()
    if args.url:
        verify_browser(args.url, deck, expected)
    else:
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            verify_browser(f"http://127.0.0.1:{server.server_port}", deck, expected)
        finally:
            server.shutdown()
            server.server_close()
