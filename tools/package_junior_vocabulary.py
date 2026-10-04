"""Package the illustrated KDF and matching Anki media without external assets."""
import base64
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/junior-themed-vocabulary-kdf-package'
OUT.mkdir(parents=True, exist_ok=True)
deck_path = ROOT / 'decks/junior-themed-vocabulary/deck.json'
deck = json.loads(deck_path.read_text(encoding='utf-8'))
shutil.copy2(deck_path, OUT / 'deck.json')
shutil.copy2(ROOT / 'outputs/junior-themed-vocabulary/conversion-report.json', OUT / 'conversion-report.json')
shutil.copy2(ROOT / 'tools/data/junior-image-generation.json', OUT / 'image-generation.json')
media = OUT / 'media'
media.mkdir(exist_ok=True)
with (OUT / 'anki.tsv').open('w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f, delimiter='\t', lineterminator='\n')
    writer.writerow(['Front', 'Back', 'Tags'])
    for c in deck['cards']:
        name = c['id'] + '.webp'
        (media / name).write_bytes(base64.b64decode(c['front']['image'].split(',', 1)[1]))
        front = html.escape(c['front']['primary']) + '<br><img src="' + name + '">'
        back = '<br>'.join(html.escape(c['back'][k]).replace('\n', '<br>') for k in ['primary', 'translation', 'phonetic', 'explanation'] if c['back'].get(k))
        writer.writerow([front, back, ' '.join(t.replace(' ', '_') for t in c['tags'])])
(OUT / '使用说明.txt').write_text('''初中主题词汇（图解版）1.1.0
769 张图文词卡，25 个主题；每张卡片都有配图。

Flashcardsmaker：打开“管理卡组”，复制 deck.json 全部内容到 JSON 输入框，点击导入。ZIP 请先解压。图片已经内嵌，不需要单独导入 media。沿用原卡片 ID，可保留学习进度。
Anki：先将 media 文件夹内的 WebP 文件复制到 Anki 用户资料的 collection.media 文件夹，再导入 anki.tsv，使用制表符、跳过第一行列名、启用 HTML；三列对应 Front、Back、Tags。含图片、释义和已有音标。

配图：668 张原 PDF 裁图、28 张采用同风格补绘图片、73 张数量和日期等示意图。抽象词与同义词可共用记忆提示图。正面为英文和图片，背面为词义、音标及修订说明。不含音频。
主词表共 825 次词条出现，去重后 769 词，不能当作 3500 词或官方 KET 词表。33 个原文无音标词条保持留空；10 处词义修订见 conversion-report.json。同词多义合并，其他主题保留为可搜索标签。
''', encoding='utf-8')
report = ROOT / 'outputs/junior-themed-vocabulary/browser-test.json'
if report.exists():
    shutil.copy2(report, OUT / 'browser-test.json')
manifest = dict(format='kdf-package/1.0', deckId=deck['deck']['id'], deckVersion=deck['deck']['version'],
    generatedAt=datetime.now(timezone.utc).isoformat(), imageCount=len(deck['cards']),
    files=sorted(str(p.relative_to(OUT)).replace('\\', '/') for p in OUT.rglob('*') if p.is_file() and p.name != 'manifest.json'),
    deckSha256=hashlib.sha256(deck_path.read_bytes()).hexdigest())
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
target = ROOT / 'outputs/初中主题词汇-图解版-KDF.zip'
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob('*'):
        if p.is_file():
            z.write(p, str(p.relative_to(OUT)))
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert z.read('deck.json') == deck_path.read_bytes()
    assert len([n for n in z.namelist() if n.startswith('media/')]) == 769
print(json.dumps(dict(package=str(target), bytes=target.stat().st_size, images=769), ensure_ascii=False))
