"""Build the themed bilingual deck from the visually transcribed image PDF.

The input is an edited transcription, not an OCR result or verbatim quotation.
No original PDF, page images, or audio are distributed by this builder.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECK_ID = 'junior-themed-vocabulary'
SOURCE = 'Ai教辅【初中常用英文3500单词】.pdf'
STAMP = '2026-10-04T12:00:00Z'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    groups, entries, page_counts = {}, {}, Counter()
    rows, duplicates, corrections = [], [], []
    for line in (ROOT / 'tools/data/junior-themed-vocabulary.txt').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('@'):
            page, topic = line[1:].split('|')
            page = int(page)
            groups.setdefault(topic, f'theme-{page:02d}')
            continue
        parts = [s.strip() for s in line.split('|')]
        assert len(parts) in (3, 4), line
        word, ipa, meaning = parts[:3]
        note = parts[3] if len(parts) == 4 else ''
        assert word and meaning and '?' not in meaning, line
        page_counts[page] += 1
        row = dict(page=page, position=page_counts[page], word=word, phonetic=ipa, meaning=meaning, topic=topic, note=note)
        rows.append(row)
        key = word.casefold()
        if key in entries:
            duplicates.append(dict(word=word, page=page, retainedId=entries[key]['id']))
        else:
            entries[key] = dict(id='junior-' + hashlib.sha256(key.encode()).hexdigest()[:12], rows=[])
        entries[key]['rows'].append(row)
        if note:
            corrections.append(dict(word=word, page=page, note=note))
    assert set(page_counts) == set(range(2, 28))
    cards = []
    for entry in entries.values():
        occurrences = entry['rows']
        first = occurrences[0]
        meanings = list(dict.fromkeys(r['meaning'] for r in occurrences))
        ipa = next((r['phonetic'] for r in occurrences if r['phonetic']), '')
        notes = list(dict.fromkeys(r['note'] for r in occurrences if r['note']))
        topics = list(dict.fromkeys(r['topic'] for r in occurrences))
        back = dict(primary=first['word'], translation='；'.join(meanings))
        if ipa:
            back['phonetic'] = '/' + ipa + '/'
        if notes:
            back['explanation'] = '\n'.join(notes)
        card = dict(id=entry['id'], type='bilingual-basic', status='published',
                    categoryId=groups[first['topic']], front=dict(primary=first['word']), back=back,
                    tags=['初中主题词汇', *topics],
                    source=dict(type='pdf', documentId=SOURCE,
                                locator='; '.join(f"p. {r['page']} · entry {r['position']}" for r in occurrences),
                                excerpt=('词条整理（非原文逐字引述）：' + first['word'] + ' — ' + '；'.join(meanings))[:420]),
                    generation=dict(method='ai', model=None, generatedAt=STAMP, reviewedAt=None))
        cards.append(card)
    categories = [dict(id=group, name=topic, label=topic, parentId=None, sortOrder=i)
                  for i, (topic, group) in enumerate(groups.items())]
    deck = dict(schemaVersion='kdf/1.0', deck=dict(id=DECK_ID, title='初中主题词汇（图解版）', version='1.0.0',
                defaultCardType='bilingual-basic', locale='zh-CN',
                description=f'据27页图解PDF整理，去重后{len(cards)}词、{len(categories)}个主题。文字词卡：英文、词义及可核对音标；不含原图插画或音频。音标已规范化，修订见卡片说明。',
                theme=dict(accent='#4568a6'), learningMode=dict(answerReveal='tap', showSource=True)),
                categories=categories, cards=cards)
    path = ROOT / 'decks' / DECK_ID / 'deck.json'
    write_json(path, deck)
    runtime = 'window.__KDF_DECKS__ = window.__KDF_DECKS__ || {};\n'
    runtime += f'window.__KDF_DECKS__["{DECK_ID}"] = ' + json.dumps(deck, ensure_ascii=False, separators=(',', ':')) + ';\n'
    (ROOT / 'data' / f'{DECK_ID}.js').write_text(runtime, encoding='utf-8')
    report = dict(source=SOURCE, pages=27, pageEntryCounts=dict(page_counts), sourceEntries=len(rows),
                  cards=len(cards), categories=len(categories), duplicatesMerged=duplicates, corrections=corrections,
                  missingPhonetic=[c['front']['primary'] for c in cards if not c['back'].get('phonetic')],
                  conversion='Image-only PDF: skill extract failed; visual transcription into bilingual-basic cards used.',
                  scope='Main vocabulary lists on pages 2–27; cover, study tips, diagram labels and examples excluded. Page 23 omits ten; no missing entries invented.',
                  excludedChineseOnlyLabels=['外公', '外婆', '舅舅', '姑姑', '外甥', '外甥女'],
                  deduplication='English term casefold; merge meanings, all source locators and topic tags; primary category is first occurrence.',
                  phonetics='IPA typography and obvious source errors normalized during visual transcription; not a verbatim quote or exhaustive dictionary verification. Missing IPA left empty.',
                  images='Text cards only. Source illustrations were not extracted into individual cards.',
                  audio='No audio in source PDF; no audio field or external pronunciation dependency.',
                  publication='Published under explicit user instruction to generate, add as builtin and deploy; no claim of separate human content review.',
                  referenceLinks=[f'https://dictionary.cambridge.org/dictionary/english-chinese-simplified/{w}' for w in ['female','parent','rather']],
                  skillAnkiExportIncludesPhonetic=False)
    if (ROOT / SOURCE).exists():
        report['sourceSha256'] = hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest()
    write_json(ROOT / 'outputs/junior-themed-vocabulary/conversion-report.json', report)
    print(json.dumps(dict(cards=len(cards), categories=len(categories), sourceEntries=len(rows), merged=len(duplicates), corrections=len(corrections), missingIPA=len(report['missingPhonetic']))))


if __name__ == '__main__':
    main()
