# 知识闪卡生成器

这是一个以 **Knowledge Deck Format（KDF）v1** 为内容标准的通用知识闪卡学习器。它从原 CFA 一级闪卡项目演进而来：保留离线学习、筛选、搜索、星标、笔记、学习状态和批量渲染，同时不再绑定 CFA 数据结构。

## 已交付能力

- **多卡组学习器**：通过 `deck-catalog.json` 注册卡组，使用 `?deck=<deck-id>` 直达。
- **KDF v1 标准**：统一描述卡组元数据、分类树、卡片类型、溯源与生成审核状态。
- **CFA 数据迁移**：原始 10 科目、1614 张 CFA 一级卡片已迁移为 `decks/cfa-level-1/deck.json`。
- **浏览器内卡组管理**：可直接导入 KDF JSON 或 KDF ZIP 卡组包，导出 KDF JSON、KDF ZIP、Anki TSV 和学习档案；导入卡组仅保存到当前浏览器本地。
- **Anki 导出**：KDF 可输出 UTF-8 TSV 文件并导入 Anki。
- **PDF 产卡 Skill**：项目内 `skills/pdf-to-kdf-flashcards/` 可将文本型 PDF 转为带页码溯源的 KDF 草稿卡包。

## 快速打开

请在项目根目录使用本地 HTTP 服务：

```bash
C:/Users/wangx/.workbuddy/binaries/python/versions/3.13.12/python.exe -m http.server 8765 --directory C:/flashcardsmaker
```

访问：

```text
http://127.0.0.1:8765
```


```

学习状态使用 `kdf:profile:<deck-id>` 保存在当前浏览器；不同卡组互不覆盖。首次打开 CFA 卡组时，应用会尝试迁移原先的 `cfa_l1_flash_v2` 本地学习状态。

## KDF 卡组规范

完整 JSON Schema 位于：`schemas/kdf-deck.schema.json`。

一个最小卡组包括：

```json
{
  "schemaVersion": "kdf/1.0",
  "deck": {
    "id": "example-deck",
    "title": "示例知识卡组",
    "version": "1.0.0",
    "defaultCardType": "basic"
  },
  "categories": [],
  "cards": []
}
```

当前支持：`basic`、`bilingual-basic`、`cloze`、`qa`、`image-vocabulary`、`formula` 和 `multiple-choice`。卡片可处于 `draft`、`validated`、`reviewed`、`published`、`archived` 状态；学习器只展示 `published` 卡片。

## 浏览器内导入与导出

点击学习器工具栏中的 **卡组管理**：

- **导入卡组**：选择 KDF v1 `.json`，或包含 `deck.json` 的 `.zip` 卡包。系统在导入前校验卡组结构，并将内容保存在浏览器本地；不会改动原始文件。
- **导出当前卡组**：可下载 KDF JSON、KDF ZIP 卡包或 Anki TSV。
- **学习档案**：可备份/恢复当前卡组的已掌握、学习中、星标与整卡笔记。恢复时卡组 ID 必须与当前卡组一致，并会覆盖当前档案。
- **删除本地卡组**：仅删除浏览器保存的导入副本，不会删除电脑上的源文件。

图片、音频等附加资源目前需要在 KDF 中使用可访问的 URL；KDF ZIP 的嵌入资源自动解包与离线引用将在下一轮补充。

## 新增一个内置卡组

1. 按 KDF v1 创建 `decks/<deck-id>/deck.json`。
2. 执行校验：

```bash
C:/Users/wangx/.workbuddy/binaries/python/versions/3.13.12/python.exe tools/validate_kdf.py decks/<deck-id>/deck.json
```

3. 在 `deck-catalog.json` 的 `decks` 数组追加：

```json
{ "id": "<deck-id>", "path": "./decks/<deck-id>/deck.json", "featured": true }
```

4. 使用 `?deck=<deck-id>` 打开。

## 数据迁移与 Anki 导出

迁移原 CFA JSON：

```bash
C:/Users/wangx/.workbuddy/binaries/python/versions/3.13.12/python.exe tools/migrate_cfa_to_kdf.py data.json decks/cfa-level-1/deck.json
```

导出 Anki TSV：

```bash
C:/Users/wangx/.workbuddy/binaries/python/versions/3.13.12/python.exe tools/export_anki_tsv.py decks/cfa-level-1/deck.json outputs/cfa-level-1-anki.tsv
```

在 Anki 导入 `TSV` 时，指定制表符分隔；第一列为 Front、第二列为 Back、第三列为 Tags。

## PDF 生成 KDF 闪卡包

阅读 `skills/pdf-to-kdf-flashcards/SKILL.md`，或直接运行：

```bash
C:/Users/wangx/.workbuddy/binaries/python/envs/default/Scripts/python.exe skills/pdf-to-kdf-flashcards/scripts/pdf_to_kdf.py extract <source.pdf> outputs/<name>-extract
C:/Users/wangx/.workbuddy/binaries/python/envs/default/Scripts/python.exe skills/pdf-to-kdf-flashcards/scripts/pdf_to_kdf.py draft <source.pdf> outputs/<name>-draft/deck.json --title "卡组名称" --max-cards 12
C:/Users/wangx/.workbuddy/binaries/python/envs/default/Scripts/python.exe skills/pdf-to-kdf-flashcards/scripts/pdf_to_kdf.py validate outputs/<name>-draft/deck.json
C:/Users/wangx/.workbuddy/binaries/python/envs/default/Scripts/python.exe skills/pdf-to-kdf-flashcards/scripts/pdf_to_kdf.py package outputs/<name>-draft/deck.json outputs/<name>-kdf-package
```

PDF 自动产出的卡默认均为 `draft`，并保留 `source.locator` 页码和 `source.excerpt` 原文片段。完成内容审核后，将确认为正式内容的卡片改为 `published`，再将该 `deck.json` 注册到 `deck-catalog.json`。

## 目录说明

| 路径 | 用途 |
|---|---|
| `index.html` / `app.js` | 通用 KDF 学习器 |
| `deck-catalog.json` | 可用卡组目录 |
| `decks/` | 每个 KDF 卡组的内容目录 |
| `schemas/kdf-deck.schema.json` | KDF v1 结构标准 |
| `tools/` | CFA 迁移、KDF 校验、Anki 导出工具 |
| `skills/pdf-to-kdf-flashcards/` | PDF 到 KDF 闪卡包生成 Skill |
| `outputs/` | 已生成的导入包和导出文件 |

## 版权与审核

请确认拥有输入 PDF、图片、音频和教材内容的处理与分发权。金融、医疗、法律等专业资料由 AI 生成的卡片必须经人工审核后才应发布。
