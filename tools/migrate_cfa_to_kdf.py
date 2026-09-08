#!/usr/bin/env python3
"""Convert the legacy CFA topics/cards JSON into a portable KDF v1 deck."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def slug(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "uncategorized"


def unique_id(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def migrate(source: Path, output: Path) -> dict:
    legacy = json.loads(source.read_text(encoding="utf-8"))
    categories: list[dict] = []
    cards: list[dict] = []
    used_category_ids: set[str] = set()
    used_card_ids: set[str] = set()

    for topic_index, topic in enumerate(legacy.get("topics", []), start=1):
        topic_name = str(topic.get("name", "Uncategorized"))
        category_id = unique_id(slug(topic_name), used_category_ids)
        categories.append({
            "id": category_id,
            "name": topic_name,
            "label": topic_name,
            "parentId": None,
            "sortOrder": topic_index,
        })
        section_ids: dict[str, str] = {}
        for card_index, source_card in enumerate(topic.get("cards", []), start=1):
            reading = str(source_card.get("reading") or "")
            if reading and reading not in section_ids:
                section_id = unique_id(f"{category_id}-{slug(reading)}", used_category_ids)
                section_ids[reading] = section_id
                categories.append({
                    "id": section_id,
                    "name": reading,
                    "label": reading,
                    "parentId": category_id,
                    "sortOrder": card_index,
                })

            raw_id = str(source_card.get("id") or f"{category_id}-{card_index:04d}")
            card_id = unique_id(raw_id, used_card_ids)
            cards.append({
                "id": card_id,
                "type": "bilingual-basic",
                "status": "published",
                "categoryId": category_id,
                "sectionId": section_ids.get(reading),
                "front": {
                    "primary": str(source_card.get("en") or ""),
                    "translation": str(source_card.get("cn") or ""),
                },
                "back": {
                    "primary": str(source_card.get("ed") or ""),
                    "translation": str(source_card.get("cd") or ""),
                },
                "tags": [category_id] + ([slug(reading)] if reading else []),
                "difficulty": 2,
                "source": {
                    "type": "curated",
                    "documentId": "cfa-level-1-legacy",
                    "locator": reading or None,
                    "excerpt": None,
                },
                "generation": {
                    "method": "import",
                    "model": None,
                    "generatedAt": None,
                    "reviewedAt": None,
                },
            })

    result = {
        "schemaVersion": "kdf/1.0",
        "deck": {
            "id": "cfa-level-1",
            "title": "CFA 一级知识闪卡",
            "description": "由原 CFA 中英对照闪卡数据迁移而来。",
            "version": str(legacy.get("version") or "1.0.0"),
            "defaultCardType": "bilingual-basic",
            "locale": "zh-CN",
            "theme": {"accent": "#0f6e56", "cover": "../../logo.jpg"},
            "learningMode": {"answerReveal": "tap", "showSource": False},
        },
        "categories": categories,
        "cards": cards,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"cards": len(cards), "categories": len(categories), "output": str(output)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy CFA JSON to KDF v1.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
