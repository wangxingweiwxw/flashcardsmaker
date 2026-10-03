#!/usr/bin/env python3
"""Verify source fidelity, every local audio asset, and browser playback/learning flows.

Requires Playwright with Microsoft Edge and ffmpeg (or imageio-ffmpeg).
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import threading

from import_word_memory import ROOT, DECK_ID, read_words, is_mp3
from validate_kdf import validate


def verify_data(decode_audio=True):
    path = ROOT / "decks" / DECK_ID / "deck.json"
    errors, warnings = validate(path)
    assert not errors and not warnings, (errors, warnings)
    deck = json.loads(path.read_text(encoding="utf-8"))
    words = read_words()
    assert len(deck["cards"]) == len(words) == 3980
    manifest = json.loads((ROOT / "outputs/word-memory-audio-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["assets"]) == len(words)
    ordered_words = [card["front"]["primary"].casefold() for card in deck["cards"]]
    assert ordered_words == sorted(ordered_words)
    by_id = {card["id"]: card for card in deck["cards"]}
    assert len(by_id) == len(words)
    for index, (word, asset) in enumerate(zip(words, manifest["assets"]), 1):
        card = by_id[f"word-memory-{index:04d}"]
        assert card["front"]["primary"] == card["back"]["primary"] == word["word"]
        assert card["back"]["translation"] == word["meaning"]
        assert card["front"]["phonetic"] == card["back"]["phonetic"] == word["pronunciation"]
        assert card["back"]["homophone"] == word["homophone"]
        assert card["back"]["explanation"] == word["memory_phrase"]
        assert card["categoryId"] == "letter-" + word["word"][0].lower()
        assert card["front"]["audio"] == card["back"]["audio"] == "./" + asset["file"]
        data = (ROOT / asset["file"]).read_bytes()
        assert is_mp3(data) and hashlib.sha256(data).hexdigest() == asset["sha256"]
    if not decode_audio:
        print("PASS: A-Z order, all 3,980 original IDs, fields and audio hashes preserved", flush=True)
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    def decode(asset):
        result = subprocess.run([ffmpeg, "-v", "error", "-xerror", "-i", str(ROOT / asset["file"]),
                                 "-f", "null", "-"], capture_output=True, timeout=20)
        assert result.returncode == 0 and not result.stderr, (asset["file"], result.stderr.decode(errors="replace"))

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(decode, manifest["assets"]))
    print("PASS: 3,980 source entries preserved; all 3,980 MP3s hash-checked and decoded", flush=True)


def verify_browser():
    from playwright.sync_api import sync_playwright

    def wait_render(page, count):
        page.wait_for_function("count => document.querySelector('#deck').getAttribute('aria-busy') === 'false' && document.querySelectorAll('.card').length === count", arg=count)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            errors, remote, media = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: media.append(request.url) if ".mp3" in request.url else None)

            def offline_only(route):
                if route.request.url.startswith(url):
                    route.continue_()
                else:
                    remote.append(route.request.url)
                    route.abort()

            context.route("**/*", offline_only)
            page.goto(url)
            page.wait_for_function("app.cards.length === 1614")
            wait_render(page, 1614)
            page.evaluate("window.renderTicks = 0; window.renderTickTimer = setInterval(function() { renderTicks++; }, 16)")
            page.select_option("#deckPicker", DECK_ID)
            page.wait_for_function("app.cards.length === 3980")
            wait_render(page, 3980)
            assert page.evaluate("clearInterval(renderTickTimer); renderTicks >= 3"), "Automatic rendering must yield to mobile input"
            assert page.locator("#loadMore").count() == 0
            desktop_ids = page.locator(".card").evaluate_all("cards => cards.map(c => c.dataset.cardId)")
            assert len(set(desktop_ids)) == 3980
            assert page.locator(".card").nth(100).locator(".front .term").inner_text().lower().startswith("a")
            assert page.locator(".card").nth(101).locator(".front .term").inner_text().lower().startswith("a")
            assert page.locator("#deckPicker option").count() == 3
            assert not media, "Audio should not preload on deck load"

            first_audio = page.locator(".front .audio-button").first
            first_audio.click()
            page.wait_for_function("activePronunciation && activePronunciation.audio.currentTime > 0")
            assert not page.locator(".card").first.evaluate("e => e.classList.contains('flipped')")
            page.wait_for_function("activePronunciation === null")
            assert first_audio.get_attribute("aria-pressed") == "false"

            # Rapid clicks must pause the previous instance; repeat click stops.
            page.evaluate("""() => {
              document.querySelectorAll('.front .audio-button')[0].click();
              window.previousAudio = activePronunciation.audio;
              document.querySelectorAll('.front .audio-button')[1].click();
            }""")
            assert page.evaluate("previousAudio.paused && !previousAudio.getAttribute('src')")
            page.locator(".front .audio-button").nth(1).click()
            assert page.evaluate("activePronunciation === null")

            page.fill("#search", "行动如神")
            wait_render(page, 1)
            page.locator(".card .front .term").first.click()
            assert "艾克神" in page.locator(".card").first.locator(".back").inner_text()
            assert "行动如神，一出手就成功" in page.locator(".card").first.locator(".back").inner_text()
            page.locator(".card").first.locator("[data-status=known]").click()
            assert page.locator("#known").inner_text() == "已掌握 1"
            page.reload()
            page.wait_for_function("app.cards.length === 3980")
            wait_render(page, 1)
            assert page.locator("#known").inner_text() == "已掌握 1"

            page.fill("#search", "行动如神")
            page.wait_for_function("document.querySelectorAll('.card').length === 1")
            page.fill("#search", "")
            wait_render(page, 3980)
            page.select_option("#filterCategory", "letter-z")
            assert page.evaluate("filteredCards().every(c => c.front.primary.toLowerCase().startsWith('z'))")
            page.select_option("#filterCategory", "all")
            wait_render(page, 3980)
            # A filter change during progressive rendering must cancel stale batches.
            page.evaluate("""() => {
              app.ui.query = ''; render();
              app.ui.query = '行动如神'; render();
            }""")
            wait_render(page, 1)
            page.wait_for_timeout(150)
            assert page.locator(".card").count() == 1
            page.evaluate("app.ui.query = ''; render()")
            wait_render(page, 3980)
            # Marking a card in the unfiltered view preserves the rest of the DOM.
            page.evaluate("window.untouchedCard = document.querySelectorAll('.card')[1]")
            page.locator(".card").first.locator(".front .term").click()
            page.locator(".card").first.locator("[data-status=learning]").click()
            assert page.evaluate("untouchedCard === document.querySelectorAll('.card')[1]")
            page.locator(".card").first.locator(".back .definition").click()

            # A missing file reports an error and permits retry.
            page.evaluate("playPronunciation('./audio/missing-test.mp3', document.querySelector('.audio-button'))")
            page.wait_for_function("activePronunciation === null")
            assert "音频无法播放" in page.locator("#toast").inner_text()
            page.locator(".front .audio-button").first.click()
            page.wait_for_function("activePronunciation && activePronunciation.audio.currentTime > 0")
            page.select_option("#deckPicker", "raz-picture-vocabulary")
            page.wait_for_function("app.cards.length === 30")
            wait_render(page, 30)
            assert page.evaluate("activePronunciation === null")
            assert page.locator(".card-image").first.evaluate("e => e.complete && e.naturalWidth > 0")
            page.select_option("#deckPicker", "cfa-level-1")
            page.wait_for_function("app.cards.length === 1614")
            wait_render(page, 1614)
            assert page.locator("#known").inner_text() == "已掌握 0"
            # A delayed, failed earlier load must not overwrite the newest deck.
            page.evaluate("""async () => {
              const original = getDeckPayload;
              getDeckPayload = function(id) {
                if (id === 'cfa-level-1') return new Promise(function(resolve, reject) {
                  setTimeout(function() { reject(new Error('stale test load')); }, 60);
                });
                return original(id);
              };
              try { await Promise.all([switchDeck('cfa-level-1'), switchDeck('raz-picture-vocabulary')]); }
              finally { getDeckPayload = original; }
            }""")
            wait_render(page, 30)
            assert page.evaluate("app.deckData.deck.id === 'raz-picture-vocabulary'")

            # File-based opening verifies relative media paths with no HTTP service.
            file_context = browser.new_context(viewport={"width": 390, "height": 844})
            file_page = file_context.new_page()
            file_page.on("pageerror", lambda error: errors.append(str(error)))
            file_page.goto((ROOT / "index.html").as_uri() + "?deck=" + DECK_ID)
            file_page.wait_for_function("app.cards.length === 3980")
            wait_render(file_page, 3980)
            assert file_page.locator(".card").evaluate_all("cards => cards.map(c => c.dataset.cardId)") == desktop_ids
            assert file_page.locator("#loadMore").count() == 0
            assert file_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            file_page.locator(".front .audio-button").first.click()
            file_page.wait_for_function("activePronunciation && activePronunciation.audio.currentTime > 0")
            file_page.wait_for_function("activePronunciation === null")
            file_page.locator(".card").nth(100).scroll_into_view_if_needed()
            file_page.screenshot(path=str(ROOT / "outputs/word-memory-mobile.png"))
            assert not errors, errors
            assert not remote, remote
            browser.close()
            print("PASS: desktop/mobile, file:// playback, no external requests, lazy audio, search, filters, progress, failure/retry, playback cancellation, CFA/RAZ regression", flush=True)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-audio-decode", action="store_true", help="Retain hash verification; skip decoding unchanged audio")
    args = parser.parse_args()
    verify_data(decode_audio=not args.skip_audio_decode)
    verify_browser()
