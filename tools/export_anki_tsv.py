#!/usr/bin/env python3
"""Export published KDF cards into UTF-8 TSV compatible with Anki import."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def clean(value: object) -> str:
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", "<br>")


def text(side: dict) -> str:
    ordered = ["prompt", "primary", "translation", "definition", "phonetic", "example", "answer", "explanation"]
    values = [clean(side[key]) for key in ordered if side.get(key)]
    if not values:
        values = [clean(value) for value in side.values() if isinstance(value, str) and value]
    return "<br>".join(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export KDF v1 deck as Anki TSV.")
    parser.add_argument("deck", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.deck.read_text(encoding="utf-8"))
    categories = {category["id"]: category.get("name", category["id"]) for category in payload.get("categories", [])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["Front", "Back", "Tags"])
        for card in payload.get("cards", []):
            if card.get("status") != "published":
                continue
            tags = list(card.get("tags") or [])
            if card.get("categoryId") in categories:
                tags.append(f"category::{categories[card['categoryId']].replace(' ', '_')}")
            if card.get("sectionId") in categories:
                tags.append(f"section::{categories[card['sectionId']].replace(' ', '_')}")
            writer.writerow([text(card.get("front", {})), text(card.get("back", {})), " ".join(dict.fromkeys(tags))])
            count += 1
    print(json.dumps({"output": str(args.output), "cards": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
