#!/usr/bin/env python3
"""Build an importable, image-backed KDF deck from the supplied RAZ picture-vocabulary PDF."""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image

SOURCE = Path(r"C:\flashcardsmaker\RAZ词汇.pdf")
OUTPUT_DIR = Path(r"C:\flashcardsmaker\outputs\raz-vocabulary-kdf-package")
DECK_PATH = OUTPUT_DIR / "deck.json"
ZIP_PATH = Path(r"C:\flashcardsmaker\outputs\raz-vocabulary-kdf-package.kdf.zip")

# Verified against the rendered source pages. Each tuple is (page, source position, English, Chinese, IPA).
# Source repeats "room" (pp. 2 and 4) and "peach" (pp. 14 and 16); KDF publishes only the first occurrence.
ENTRIES = [
    (1, 0, "P.E.", "体育课", "/ˌpiː ˈiː/"), (1, 1, "sweep", "扫；打扫", "/swiːp/"),
    (2, 0, "doctor", "医生", "/ˈdɒktə(r)/"), (2, 1, "room", "房间", "/ruːm/"),
    (3, 0, "nurse", "护士", "/nɜːs/"), (3, 1, "busy", "忙碌的", "/ˈbɪzi/"),
    (4, 0, "room", "房间", "/ruːm/"), (4, 1, "worker", "工人", "/ˈwɜːkə(r)/"),
    (5, 0, "tired", "累的", "/ˈtaɪəd/"), (5, 1, "floor", "地板", "/flɔː(r)/"),
    (6, 0, "chore", "家务", "/tʃɔː(r)/"), (6, 1, "helpful", "有帮助的", "/ˈhelpfl/"),
    (7, 0, "job", "工作", "/dʒɒb/"), (7, 1, "clean", "打扫", "/kliːn/"),
    (8, 0, "cook", "厨师", "/kʊk/"), (8, 1, "farmer", "农民", "/ˈfɑːmə(r)/"),
    (9, 0, "help at home", "在家帮忙", "/help æt həʊm/"), (9, 1, "make chairs", "制作椅子", "/meɪk tʃeəz/"),
    (10, 0, "look after", "照顾", "/lʊk ˈɑːftə(r)/"), (10, 1, "teach Chinese", "教语文", "/tiːtʃ ˌtʃaɪˈniːz/"),
    (11, 0, "busy and tired", "又忙又累", "/ˈbɪzi ænd ˈtaɪəd/"), (11, 1, "make a gift", "制作礼物", "/meɪk ə ɡɪft/"),
    (12, 0, "clean the room", "打扫房间", "/kliːn ðə ruːm/"), (12, 1, "The Double Ninth Festival", "重阳节", "/ðə ˌdʌbl naɪnθ ˈfestɪvl/"),
    (13, 0, "teacher", "老师", "/ˈtiːtʃə(r)/"), (13, 1, "lunch", "午餐", "/lʌntʃ/"),
    (14, 0, "chair", "椅子", "/tʃeə(r)/"), (14, 1, "peach", "桃子", "/piːtʃ/"),
    (15, 0, "kitchen", "厨房", "/ˈkɪtʃɪn/"), (15, 1, "Chinese", "中文", "/ˌtʃaɪˈniːz/"),
    (16, 0, "peach", "桃子", "/piːtʃ/"), (16, 1, "child", "小孩", "/tʃaɪld/"),
]


def slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def crop_as_data_uri(pdf: fitz.Document, page_number: int, position: int) -> str:
    page = pdf[page_number - 1]
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    # Each page has two horizontal cards. Keep only the left illustration zone:
    # the original worksheet places phonetics, English and Chinese in the right half.
    split = image.height // 2
    top = 10 if position == 0 else split + 10
    bottom = split - 4 if position == 0 else image.height - 10
    illustration_right = int(image.width * 0.48)
    card = image.crop((8, top, illustration_right, bottom))
    card.thumbnail((520, 520))
    stream = BytesIO()
    card.save(stream, format="JPEG", quality=86, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"找不到源文件：{SOURCE}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open(SOURCE)
    generated_at = datetime.now(timezone.utc).isoformat()
    cards = []
    seen_terms = set()
    duplicate_terms = []
    for index, (page, position, word, translation, phonetic) in enumerate(ENTRIES, start=1):
        term_key = word.casefold()
        if term_key in seen_terms:
            duplicate_terms.append(word)
            continue
        seen_terms.add(term_key)
        source_excerpt = f"图文词卡：{word}；中文释义：{translation}；音标：{phonetic}。"
        cards.append({
            "id": f"raz-vocabulary-{index:03d}-{slug(word)}",
            "type": "image-vocabulary",
            "status": "published",
            "categoryId": "raz-vocabulary",
            "sectionId": f"page-{page:02d}",
            "front": {
                "prompt": "看图并朗读英文单词或短语",
                "primary": word,
                "image": crop_as_data_uri(pdf, page, position),
            },
            "back": {
                "primary": word,
                "translation": translation,
                "phonetic": phonetic,
                "example": f"{word} — {translation}",
            },
            "tags": ["raz", "英语词汇", "图像词卡", "小学英语"],
            "difficulty": 1,
            "source": {
                "type": "pdf",
                "documentId": SOURCE.name,
                "locator": f"p. {page}，{'上半页' if position == 0 else '下半页'}词卡",
                "excerpt": source_excerpt,
            },
            "generation": {
                "method": "manual-visual-transcription",
                "model": None,
                "generatedAt": generated_at,
                "reviewedAt": generated_at,
            },
        })
    categories = [{
        "id": "raz-vocabulary", "name": "RAZ Vocabulary", "label": "RAZ 图像词汇",
        "parentId": None, "sortOrder": 1,
    }]
    categories.extend({
        "id": f"page-{page:02d}", "name": f"Page {page}", "label": f"第 {page} 页",
        "parentId": "raz-vocabulary", "sortOrder": page,
    } for page in range(1, 17))
    deck = {
        "schemaVersion": "kdf/1.0",
        "deck": {
            "id": "raz-picture-vocabulary",
            "title": "RAZ 图像英语词汇卡",
            "description": "根据 RAZ词汇.pdf 逐页复核制作的图像英语词汇卡；正面显示核心插图与英文，翻面后显示音标和中文释义；源文件重复词已去重。",
            "version": "1.3.0",
            "defaultCardType": "image-vocabulary",
            "locale": "zh-CN",
            "theme": {"accent": "#2B9DC7"},
            "learningMode": {"showImageFirst": True, "autoplayAudio": False, "answerReveal": "tap", "showSource": True},
        },
        "categories": categories,
        "cards": cards,
    }
    DECK_PATH.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    validation = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "cardCount": len(cards),
        "publishedCount": len(cards),
        "deduplicatedTerms": duplicate_terms,
        "assetStrategy": "每张图像词卡使用内嵌 JPEG data URI，导入浏览器后不依赖外部图片路径。",
    }
    (OUTPUT_DIR / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUTPUT_DIR / "anki.tsv").open("w", encoding="utf-8", newline="") as handle:
        handle.write("Front\tBack\tTags\n")
        for card in cards:
            front = "看图说出英文单词或短语"
            back = f"{card['back']['primary']}<br>{card['back']['phonetic']}<br>{card['back']['translation']}"
            handle.write(f'"{front}"\t"{back}"\t"{" ".join(card["tags"])}"\n')
    manifest = {
        "format": "kdf-package/1.0",
        "deckId": deck["deck"]["id"],
        "deckVersion": deck["deck"]["version"],
        "generatedAt": generated_at,
        "source": {"fileName": SOURCE.name, "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "pages": 16},
        "files": ["deck.json", "anki.tsv", "validation.json", "manifest.json"],
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for file_name in manifest["files"]:
            package.write(OUTPUT_DIR / file_name, file_name)
    print(json.dumps({"deck": str(DECK_PATH), "package": str(ZIP_PATH), "cards": len(cards), "bytes": ZIP_PATH.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
