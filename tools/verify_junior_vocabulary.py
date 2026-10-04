"""Check source accounting, builtin rendering, and actual JSON import on desktop/mobile."""
import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ID = 'junior-themed-vocabulary'
parser = argparse.ArgumentParser()
parser.add_argument('--url')
args = parser.parse_args()
base = args.url.rstrip('/') + '/' if args.url else (ROOT / 'index.html').as_uri()
expected = json.loads((ROOT / f'decks/{ID}/deck.json').read_text(encoding='utf-8'))
cards = expected['cards']
assert len(cards) == 769 and len(expected['categories']) == 25
assert len({c['front']['primary'].casefold() for c in cards}) == len(cards)
assert sum(not c['back'].get('phonetic') for c in cards) == 33
assert all(c['status'] == 'published' and c['source']['type'] == 'pdf' for c in cards)
assert all(not c['front'].get('audio') and not c['back'].get('audio') for c in cards)
assert expected['deck']['version'] == '1.1.0'
for card in cards:
    assert card['type'] == 'image-vocabulary'
    uri = card['front']['image']
    assert uri.startswith('data:image/webp;base64,')
    with Image.open(BytesIO(base64.b64decode(uri.split(',', 1)[1], validate=True))) as image:
        image.load()
        assert image.width > 0 and image.height > 0
by_word = {c['front']['primary']: c for c in cards}
assert by_word['chemist']['back']['translation'] == '药剂师；化学家'
assert by_word['pen']['back']['translation'] == '钢笔'
assert '女性' == by_word['female']['back']['translation']
assert '秒' in by_word['second']['back']['translation']
assert 'p. 10' in by_word['paper']['source']['locator'] and 'p. 11' in by_word['paper']['source']['locator']


def wait_render(page, count):
    page.wait_for_function("n => document.querySelector('#deck').getAttribute('aria-busy') === 'false' && document.querySelectorAll('.card').length === n", arg=count)


def check_images(page):
    # Lazy images outside the viewport must also be decoded before acceptance.
    page.locator('.card-image').evaluate_all("imgs=>imgs.forEach(i=>i.loading='eager')")
    page.wait_for_function("()=>document.querySelectorAll('.card-image').length===769 && [...document.querySelectorAll('.card-image')].every(i=>i.complete && i.naturalWidth>0)", timeout=60000)


def settings(page, width):
    if width == 390 and not page.locator('#deckPicker').is_visible():
        page.locator('#settingsToggle').click()


results = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    for width, height in [(1280, 900), (390, 844)]:
        context = browser.new_context(viewport=dict(width=width, height=height))
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('dialog', lambda dialog: dialog.accept())
        page.goto(base + '?deck=' + ID)
        wait_render(page, 769)
        check_images(page)
        page.screenshot(path=str(ROOT / f'outputs/junior-images-{width}.png'))
        assert page.evaluate('app.deckData') == expected
        assert page.locator('.card').evaluate_all('cs=>cs.map(c=>c.dataset.cardId)') == [c['id'] for c in cards]
        assert page.locator('#deckPicker option').count() == 5
        assert page.locator('#loadMore').count() == page.locator('.audio-button').count() == 0
        settings(page, width)
        for category in expected['categories']:
            page.select_option('#filterCategory', category['id'])
            matching = [c['id'] for c in cards if c['categoryId'] == category['id']]
            wait_render(page, len(matching))
            assert page.locator('.card').evaluate_all('cs=>cs.map(c=>c.dataset.cardId)') == matching
        page.select_option('#filterCategory', 'all')
        page.fill('#search', 'female')
        wait_render(page, 1)
        page.locator('.front .term').click()
        assert '/ˈfiːmeɪl/' in page.locator('.card .back').inner_text()
        assert '女性' in page.locator('.card .back').inner_text()
        page.locator('[data-status=known]').click()
        page.locator('.card .note').fill('junior persistence check')
        page.locator('.card .note').blur()
        page.reload()
        wait_render(page, 1)
        assert page.locator('#known').inner_text() == '已掌握 1'
        assert page.locator('.card .note').input_value() == 'junior persistence check'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(ROOT / f'outputs/junior-builtin-{width}.png'))
        settings(page, width)
        page.fill('#search', '')
        wait_render(page, 769)
        for deck_id, count in [('ket-vocabulary-1624', 1624), ('word-memory-v2', 3980), ('raz-picture-vocabulary', 30), ('cfa-level-1', 1614)]:
            settings(page, width)
            page.select_option('#deckPicker', deck_id)
            wait_render(page, count)
            assert page.locator('#known').inner_text() == '已掌握 0'
        # Import the delivered package through the app's real importer.
        settings(page, width)
        page.locator('#manageDecks').click()
        package_deck = ROOT / 'outputs/junior-themed-vocabulary-kdf-package/deck.json'
        import_deck = package_deck if package_deck.exists() else ROOT / f'decks/{ID}/deck.json'
        deck_text = import_deck.read_text(encoding='utf-8')
        page.locator('#importDeckText').evaluate("(el,text)=>{el.value=text;el.dispatchEvent(new Event('input',{bubbles:true}))}", deck_text)
        page.locator('#importDeckPaste').click()
        wait_render(page, 769)
        assert page.evaluate(f'app.importedDecks["{ID}"].deck') == expected
        assert page.locator('#known').inner_text() == '已掌握 1'
        page.reload()
        wait_render(page, 769)
        assert page.evaluate('app.deckData') == expected
        assert not errors, errors
        check_images(page)
        results.append(dict(viewport=width, cardCount=769, decodedImages=769, all25Categories=True, jsonImport=True, reload=True, existing4Decks=True, errors=errors))
        context.close()
        print(f'PASS {width}px: 769 cards in order, 25 filters, IPA, progress, JSON import and previous 4 decks', flush=True)
    browser.close()
(ROOT / 'outputs/junior-themed-vocabulary/browser-test.json').write_text(json.dumps(dict(url=base, results=results,
    inputMethod='Textarea populated via DOM, followed by the real import button; clipboard paste latency not measured.'), ensure_ascii=False, indent=2), encoding='utf-8')
