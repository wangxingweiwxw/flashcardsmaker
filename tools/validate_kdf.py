#!/usr/bin/env python3
"""Dependency-free semantic validator for Knowledge Deck Format (KDF) v1."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CARD_TYPES = {"basic", "bilingual-basic", "cloze", "qa", "image-vocabulary", "formula", "multiple-choice"}
STATUSES = {"draft", "validated", "reviewed", "published", "archived"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(deck_path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        payload = json.loads(deck_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"无法解析 JSON：{exc}"], warnings

    if payload.get("schemaVersion") != "kdf/1.0":
        errors.append("schemaVersion 必须为 kdf/1.0")
    meta = payload.get("deck")
    if not isinstance(meta, dict):
        errors.append("deck 必须是对象")
    else:
        for key in ("id", "title", "version", "defaultCardType"):
            if not nonempty(meta.get(key)):
                errors.append(f"deck.{key} 必填且必须为非空字符串")
        if meta.get("defaultCardType") not in CARD_TYPES:
            errors.append("deck.defaultCardType 不在支持的卡片类型中")

    categories = payload.get("categories")
    cards = payload.get("cards")
    if not isinstance(categories, list):
        errors.append("categories 必须是数组")
        categories = []
    if not isinstance(cards, list) or not cards:
        errors.append("cards 必须是非空数组")
        cards = []

    category_ids = set()
    for index, category in enumerate(categories):
        if not isinstance(category, dict):
            errors.append(f"categories[{index}] 必须是对象")
            continue
        category_id = category.get("id")
        if not nonempty(category_id):
            errors.append(f"categories[{index}].id 缺失")
        elif category_id in category_ids:
            errors.append(f"分类 ID 重复：{category_id}")
        else:
            category_ids.add(category_id)
        if not nonempty(category.get("name")):
            errors.append(f"categories[{index}].name 缺失")

    for index, category in enumerate(categories):
        if isinstance(category, dict) and category.get("parentId") and category["parentId"] not in category_ids:
            errors.append(f"categories[{index}].parentId 指向不存在的分类：{category['parentId']}")

    card_ids = set()
    published = 0
    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        card_id = card.get("id")
        if not nonempty(card_id) or not ID_RE.match(card_id):
            errors.append(f"{prefix}.id 无效")
        elif card_id in card_ids:
            errors.append(f"卡片 ID 重复：{card_id}")
        else:
            card_ids.add(card_id)
        if card.get("type") not in CARD_TYPES:
            errors.append(f"{prefix}.type 不支持：{card.get('type')}")
        if card.get("status") not in STATUSES:
            errors.append(f"{prefix}.status 不支持：{card.get('status')}")
        elif card.get("status") == "published":
            published += 1
        if card.get("categoryId") and card["categoryId"] not in category_ids:
            errors.append(f"{prefix}.categoryId 指向不存在的分类：{card['categoryId']}")
        if card.get("sectionId") and card["sectionId"] not in category_ids:
            errors.append(f"{prefix}.sectionId 指向不存在的分类：{card['sectionId']}")
        front, back = card.get("front"), card.get("back")
        if not isinstance(front, dict) or not front:
            errors.append(f"{prefix}.front 必须是非空对象")
        if not isinstance(back, dict) or not back:
            errors.append(f"{prefix}.back 必须是非空对象")
        if isinstance(front, dict) and not any(nonempty(v) for v in front.values() if isinstance(v, str)):
            warnings.append(f"{prefix}.front 没有可展示的文本")
        if isinstance(back, dict) and not any(nonempty(v) for v in back.values() if isinstance(v, str)):
            warnings.append(f"{prefix}.back 没有可展示的文本")
        difficulty = card.get("difficulty")
        if difficulty is not None and (not isinstance(difficulty, int) or difficulty < 1 or difficulty > 5):
            errors.append(f"{prefix}.difficulty 必须为 1 至 5 的整数")

    if cards and not published:
        warnings.append("没有 published 卡片；学习器默认不会显示草稿卡")
    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a KDF v1 deck.")
    parser.add_argument("deck", type=Path)
    args = parser.parse_args()
    errors, warnings = validate(args.deck)
    result = {"deck": str(args.deck), "valid": not errors, "errors": errors, "warnings": warnings}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
