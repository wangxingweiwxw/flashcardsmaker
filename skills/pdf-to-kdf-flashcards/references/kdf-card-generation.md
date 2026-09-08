# KDF card-generation reference

## Required KDF fields

Every output deck must contain `schemaVersion`, `deck`, `categories`, and `cards`. Use `kdf/1.0` as the schema version. Each card must contain `id`, `type`, `status`, `front`, and `back`.

## Recommended generated-card shape

```json
{
  "id": "source-slug-p001-c01",
  "type": "basic",
  "status": "draft",
  "categoryId": "source-pages",
  "sectionId": "pages-001-002",
  "front": { "primary": "Question that tests one fact or relationship" },
  "back": { "primary": "Short answer", "explanation": "Optional clarification" },
  "tags": ["pdf-generated"],
  "difficulty": 2,
  "source": {
    "type": "pdf",
    "documentId": "source.pdf",
    "locator": "pp. 1-2",
    "excerpt": "Evidence text, truncated to 420 characters."
  },
  "generation": {
    "method": "ai",
    "model": "model identifier or null",
    "generatedAt": "ISO 8601 timestamp or null",
    "reviewedAt": null
  }
}
```

## Quality checklist

- Formulate a direct question or unambiguous term on the front.
- Keep the answer independently understandable.
- Avoid cards that ask for two or more unrelated facts.
- Use the source excerpt to support the answer, not merely the question topic.
- Avoid turning headers, page numbers, contents lists, or legal boilerplate into cards.
- For finance, law, medicine, and safety topics, retain `draft` status until subject-matter review.
