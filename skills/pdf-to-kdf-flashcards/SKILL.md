---
name: pdf-to-kdf-flashcards
description: This skill should be used when a user asks to turn a PDF, textbook chapter, lecture handout, or technical paper into a validated KDF v1 knowledge-flashcard JSON deck that can be imported into the Knowledge Flashcard Generator or exported to Anki.
agent_created: true
version: 1.1.0
---

# PDF to KDF flashcards

Convert a text-based PDF into a reviewable Knowledge Deck Format (KDF) v1 flashcard package. Keep source provenance on every generated card and publish no AI-generated card without an explicit review decision.

## Workflow

1. Inspect the PDF with `scripts/pdf_to_kdf.py extract <pdf> <output-dir>`.
2. If no text can be extracted, render a low-resolution contact sheet to identify whether it is an image-only worksheet or picture-vocabulary PDF. For a visually legible vocabulary worksheet, manually transcribe each term and translation, crop the source card art, and embed each crop as a data URI in the KDF `front.image` field so the ZIP remains importable without asset extraction. Do not infer unreadable text; ask for OCR or a clearer source instead.
3. For `image-vocabulary` cards, crop only the illustration zone, excluding all printed word, phonetic and translation regions. Still retain the verified target English term in `front.primary`: the learning surface displays this as clean HTML text alongside the picture. Keep phonetics, translation and explanation in `back` only.
4. Before publishing an image-vocabulary deck, generate a labeled contact sheet containing every source card with its page/position, then compare each image with the corresponding English and Chinese fields. Correct the mapping explicitly rather than assuming sequential order. De-duplicate terms case-insensitively; record skipped duplicate source terms in `validation.json`.
5. Read `references/kdf-card-generation.md` before creating cards.
6. Select the intended deck title, audience, language, card type, and target number of cards. Default to `basic`, `draft`, and 12 cards for a first pass.
7. Generate candidate cards from the extracted chunks. Use only claims that are supported by a chunk. Set each card's `source.type` to `pdf`, `source.documentId` to the source filename, and `source.locator` to the page range.
8. Save candidates as a KDF v1 JSON deck and run `scripts/pdf_to_kdf.py validate <deck.json>`.
9. Present the draft deck for review. Change only approved cards from `draft` to `published`.
10. Build an importable package with `scripts/pdf_to_kdf.py package <deck.json> <output-dir>`. The package contains `deck.json`, `manifest.json`, `validation.json`, and Anki-compatible `anki.tsv`.

## Deterministic fallback

Run `scripts/pdf_to_kdf.py draft <pdf> <deck.json> --title <title>` when no model-backed generation is available. This creates source-grounded draft cards from page chunks. Treat them as editorial starting material, not finished study content.

## Guardrails

- Reject encrypted or unreadable PDFs. For image-only PDFs, use the visual vocabulary workflow only when every term is legible enough to verify; otherwise request OCR text or a clearer source.
- For image-vocabulary cards, require `front.primary` (English target) and `front.image` (text-free illustration); require `back.translation`, and retain `back.phonetic` when supplied by the source.
- Keep one recall target per card. Split compound questions.
- Keep answers concise; move context into `back.explanation` rather than producing paragraph-length answers.
- Preserve a source excerpt of at most 420 characters per card.
- Mark every automated card as `draft` until human review.
- Do not include copyrighted source PDFs or raw source text in a public deck package unless distribution rights are clear.

## Outputs

- `extracted.json`: page-aware text chunks for inspection.
- `deck.json`: canonical KDF v1 draft or published deck.
- `validation.json`: semantic validation result.
- `anki.tsv`: UTF-8 TSV with Front, Back, Tags columns.
- `manifest.json`: package metadata and source checksum.
