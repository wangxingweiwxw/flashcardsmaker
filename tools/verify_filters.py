"""Regression checks for saved filters, search cancellation and letter counts."""
import argparse
import json
from pathlib import Path
import re
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--url')
args = parser.parse_args()
base = args.url.rstrip('/') + '/' if args.url else (ROOT / 'index.html').as_uri()
cards = json.loads((ROOT / 'decks/word-memory-v2/deck.json').read_text(encoding='utf-8'))['cards']
ids = [c['id'] for c in cards]
counts = {c['id']: len(re.findall('[a-zA-Z]', c['front']['primary'])) for c in cards}


def wait(page, count):
    page.wait_for_function("n=>document.querySelector('#deck').getAttribute('aria-busy')==='false' && document.querySelectorAll('.card').length===n", arg=count)


def settings(page):
    if not page.locator('#search').is_visible():
        page.locator('#settingsToggle').click()


def dom_ids(page):
    return page.locator('.card').evaluate_all('cs=>cs.map(c=>c.dataset.cardId)')


def switch(page, deck_id):
    settings(page)
    page.select_option('#deckPicker', deck_id)
    page.wait_for_function('id=>app.deckData.deck.id===id', arg=deck_id)


results = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    for width in [1280, 390]:
        context = browser.new_context(viewport={'width': width, 'height': 900})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(base + '?deck=word-memory-v2')
        wait(page, 3980)
        assert dom_ids(page) == ids
        settings(page)
        # Reproduce the formerly empty input with an active, invisible saved query.
        page.fill('#search', '行动如神')
        wait(page, 1)
        switch(page, 'raz-picture-vocabulary')
        wait(page, 30)
        assert page.locator('#search').input_value() == ''
        assert page.locator('#filterLetterCount').is_hidden()
        switch(page, 'word-memory-v2')
        wait(page, 1)
        assert page.locator('#search').input_value() == '行动如神'
        settings(page)
        page.fill('#search', '')
        wait(page, 3980)
        assert dom_ids(page) == ids
        # Browser search-clear events also restore the complete, ordered list.
        page.fill('#search', '行动如神')
        wait(page, 1)
        page.locator('#search').evaluate("el=>{el.value='';el.dispatchEvent(new Event('search',{bubbles:true}))}")
        wait(page, 3980)
        assert dom_ids(page) == ids
        options = page.locator('#filterLetterCount option').evaluate_all("os=>os.map(o=>o.value)")
        assert options == ['all'] + [str(n) for n in sorted(set(counts.values()))]
        for length in [3, 6, max(counts.values())]:
            page.select_option('#filterLetterCount', str(length))
            expected = [c['id'] for c in cards if counts[c['id']] == length]
            wait(page, len(expected))
            assert dom_ids(page) == expected
        page.select_option('#filterLetterCount', '6')
        page.select_option('#filterCategory', 'letter-a')
        expected = [c['id'] for c in cards if counts[c['id']] == 6 and c['categoryId'] == 'letter-a']
        wait(page, len(expected))
        assert dom_ids(page) == expected
        page.fill('#search', '行动如神')
        wait(page, 1)
        page.locator('.front .term').click()
        page.locator('[data-status=known]').click()
        page.locator('.card .note').fill('keep this note')
        page.locator('.card .note').blur()
        page.select_option('#filterStatus', 'known')
        wait(page, 1)
        page.reload()
        wait(page, 1)
        assert page.locator('#filterLetterCount').input_value() == '6'
        assert page.locator('#filterCategory').input_value() == 'letter-a'
        assert page.locator('#filterStatus').input_value() == 'known'
        assert page.locator('#search').input_value() == '行动如神'
        saved_profile = page.evaluate('JSON.stringify(app.profile)')
        settings(page)
        page.locator('#shuffle').click()
        # Clear while a search debounce and incremental render are both pending.
        page.locator('#search').evaluate("el=>{el.value='no-match-xyz';el.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#clearFilters').click()}")
        wait(page, 3980)
        assert dom_ids(page) == ids
        assert page.evaluate('JSON.stringify(app.profile)') == saved_profile
        assert page.locator('#known').inner_text() == '已掌握 1'
        assert page.locator('#search').input_value() == ''
        assert page.locator('#filterLetterCount').input_value() == 'all'
        assert page.locator('#filterCategory').input_value() == 'all'
        assert page.locator('#filterStatus').input_value() == 'all'
        # Switching immediately after typing must cancel the pending search.
        page.evaluate("()=>{let el=document.querySelector('#search');el.value='zzpending';el.dispatchEvent(new Event('input',{bubbles:true}));return switchDeck('ket-vocabulary-1624')}")
        wait(page, 1624)
        assert page.locator('#search').input_value() == ''
        assert page.evaluate("app.ui.query==='' && app.ui.letterCount==='all'")
        switch(page, 'word-memory-v2')
        wait(page, 0)
        settings(page)
        assert page.locator('#search').input_value() == 'zzpending'
        page.locator('#clearFilters').click()
        wait(page, 3980)
        page.reload()
        wait(page, 3980)
        assert dom_ids(page) == ids
        assert page.evaluate('JSON.stringify(app.profile)') == saved_profile
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        settings(page)
        assert page.locator('.toolbar .button').evaluate_all('buttons=>buttons.every(b=>b.getBoundingClientRect().height<=50)')
        page.screenshot(path=str(ROOT / f'outputs/filters-{width}.png'))
        assert not errors, errors
        results.append(dict(width=width, cards=3980, savedFilters=True, pendingSearchCancellation=True, letterCountCombinations=True, originalOrder=True, progressPreserved=True, errors=errors))
        context.close()
        print(f'PASS {width}: filter restoration, clearing, letter counts, ordering and progress', flush=True)
    browser.close()
(ROOT / 'outputs/filter-test.json').write_text(json.dumps(dict(url=base, results=results), indent=2)+'\n', encoding='utf-8')
