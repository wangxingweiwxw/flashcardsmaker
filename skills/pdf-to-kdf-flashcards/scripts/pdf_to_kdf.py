#!/usr/bin/env python3
"""Create, validate and package source-grounded KDF v1 flashcard decks from text-based PDFs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as exc:
    raise SystemExit("缺少 pypdf。请在隔离环境安装：pip install pypdf") from exc


def slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if cleaned:
        return cleaned
    return f"deck-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]}"


def extract(pdf_path: Path, chunk_size: int = 1200) -> list[dict]:
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("输入文件不是 PDF。请先解压归档并提供其中的 .pdf 文件。")
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise ValueError(f"无法读取 PDF：{exc}") from exc
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        paragraphs = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"\n\s*\n|(?<=[.!?])\s{2,}", text) if item.strip()]
        buffer, chunks = "", []
        for paragraph in paragraphs:
            candidate = f"{buffer} {paragraph}".strip()
            if buffer and len(candidate) > chunk_size:
                chunks.append(buffer)
                buffer = paragraph
            else:
                buffer = candidate
        if buffer:
            chunks.append(buffer)
        pages.append({"page": number, "chunks": chunks})
    if not pages:
        raise ValueError("PDF 未提取到文本，可能是扫描件、加密文件或空文档。")
    return pages


def first_sentences(text: str, limit: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    return " ".join(sentence.strip() for sentence in sentences[:limit] if sentence.strip())


def title_from_text(text: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text)
    return " ".join(words[:7]) or "该页面的核心内容"


def draft_deck(pdf_path: Path, title: str, max_cards: int = 12) -> dict:
    pages = extract(pdf_path)
    cards = []
    for page in pages:
        for chunk_index, chunk in enumerate(page["chunks"], start=1):
            if len(cards) >= max_cards:
                break
            answer = first_sentences(chunk)
            if len(answer) < 36:
                continue
            key_phrase = title_from_text(chunk)
            card_id = f"{slug(pdf_path.stem)}-p{page['page']:03d}-c{chunk_index:02d}"
            cards.append({
                "id": card_id,
                "type": "basic",
                "status": "draft",
                "categoryId": "source-pages",
                "sectionId": f"pages-{page['page']:03d}",
                "front": {"primary": f"根据资料，如何概括“{key_phrase}”这一段的核心内容？"},
                "back": {"primary": answer, "explanation": "请审核后将问题改写为单一、可回忆的知识点。"},
                "tags": ["pdf-generated", "needs-review"],
                "difficulty": 2,
                "source": {"type": "pdf", "documentId": pdf_path.name, "locator": f"p. {page['page']}", "excerpt": chunk[:420]},
                "generation": {"method": "ai", "model": None, "generatedAt": datetime.now(timezone.utc).isoformat(), "reviewedAt": None}
            })
        if len(cards) >= max_cards:
            break
    if not cards:
        raise ValueError("没有得到可用的候选卡，请检查 PDF 文本质量。")
    return {
        "schemaVersion": "kdf/1.0",
        "deck": {"id": slug(title), "title": title, "description": f"从 {pdf_path.name} 提取的待审核知识闪卡。", "version": "0.1.0-draft", "defaultCardType": "basic", "locale": "zh-CN", "theme": {"accent": "#0f6e56"}, "learningMode": {"answerReveal": "tap", "showSource": True}},
        "categories": [{"id": "source-pages", "name": "Source pages", "label": "来源页面", "parentId": None, "sortOrder": 1}] + [{"id": f"pages-{page['page']:03d}", "name": f"Page {page['page']}", "label": f"第 {page['page']} 页", "parentId": "source-pages", "sortOrder": page['page']} for page in pages],
        "cards": cards
    }


def validate(payload: dict) -> dict:
    errors, warnings = [], []
    if payload.get("schemaVersion") != "kdf/1.0": errors.append("schemaVersion 必须为 kdf/1.0")
    categories = payload.get("categories") if isinstance(payload.get("categories"), list) else []
    cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
    ids = [item.get("id") for item in cards if isinstance(item, dict)]
    if len(ids) != len(set(ids)): errors.append("card id 存在重复")
    category_ids = {item.get("id") for item in categories if isinstance(item, dict)}
    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict): errors.append(f"{prefix} 不是对象"); continue
        if not card.get("id"): errors.append(f"{prefix}.id 缺失")
        if card.get("status") not in {"draft", "validated", "reviewed", "published", "archived"}: errors.append(f"{prefix}.status 无效")
        if not card.get("front") or not card.get("back"): errors.append(f"{prefix} 缺少 front/back")
        if card.get("categoryId") and card["categoryId"] not in category_ids: errors.append(f"{prefix}.categoryId 无效")
        source = card.get("source") or {}
        if source.get("type") == "pdf" and (not source.get("locator") or not source.get("excerpt")): errors.append(f"{prefix} 缺少 PDF 溯源字段")
        if card.get("status") == "draft": warnings.append(f"{prefix} 仍是 draft，不能视为正式学习内容")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "cardCount": len(cards)}


def write_anki(deck: dict, path: Path) -> None:
    def side_text(side: dict) -> str:
        return "<br>".join(str(side[key]).replace("\n", "<br>") for key in ("primary", "translation", "explanation") if side.get(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["Front", "Back", "Tags"])
        for card in deck["cards"]:
            if card.get("status") == "archived": continue
            writer.writerow([side_text(card.get("front", {})), side_text(card.get("back", {})), " ".join(card.get("tags", []))])


def command_extract(args: argparse.Namespace) -> None:
    pages = extract(args.pdf)
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output / "extracted.json"
    output.write_text(json.dumps({"source": args.pdf.name, "pages": pages}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "pages": len(pages), "chunks": sum(len(page["chunks"]) for page in pages)}, ensure_ascii=False))


def command_draft(args: argparse.Namespace) -> None:
    deck = draft_deck(args.pdf, args.title, args.max_cards)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cards": len(deck["cards"]), "status": "draft"}, ensure_ascii=False))


def command_validate(args: argparse.Namespace) -> None:
    deck = json.loads(args.deck.read_text(encoding="utf-8"))
    result = validate(deck)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["valid"]: raise SystemExit(1)


def command_package(args: argparse.Namespace) -> None:
    deck = json.loads(args.deck.read_text(encoding="utf-8"))
    result = validate(deck)
    if not result["valid"]: raise SystemExit("校验失败，无法打包")
    args.output.mkdir(parents=True, exist_ok=True)
    copied_deck = args.output / "deck.json"
    shutil.copy2(args.deck, copied_deck)
    write_anki(deck, args.output / "anki.tsv")
    (args.output / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"format": "kdf-package/1.0", "deckId": deck["deck"]["id"], "deckVersion": deck["deck"]["version"], "generatedAt": datetime.now(timezone.utc).isoformat(), "files": ["deck.json", "anki.tsv", "validation.json"], "deckSha256": hashlib.sha256(copied_deck.read_bytes()).hexdigest()}
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cards": len(deck["cards"]), "valid": True}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF to KDF flashcard tooling")
    sub = parser.add_subparsers(required=True)
    extract_cmd = sub.add_parser("extract"); extract_cmd.add_argument("pdf", type=Path); extract_cmd.add_argument("output", type=Path); extract_cmd.set_defaults(func=command_extract)
    draft_cmd = sub.add_parser("draft"); draft_cmd.add_argument("pdf", type=Path); draft_cmd.add_argument("output", type=Path); draft_cmd.add_argument("--title", required=True); draft_cmd.add_argument("--max-cards", type=int, default=12); draft_cmd.set_defaults(func=command_draft)
    validate_cmd = sub.add_parser("validate"); validate_cmd.add_argument("deck", type=Path); validate_cmd.set_defaults(func=command_validate)
    package_cmd = sub.add_parser("package"); package_cmd.add_argument("deck", type=Path); package_cmd.add_argument("output", type=Path); package_cmd.set_defaults(func=command_package)
    args = parser.parse_args(); args.func(args)

if __name__ == "__main__": main()
