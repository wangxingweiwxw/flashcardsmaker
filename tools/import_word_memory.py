#!/usr/bin/env python3
"""Convert the supplied word-memory HTML to KDF and cache its pronunciation audio.

Run from any directory: python tools/import_word_memory.py
Existing MP3s are reused; --offline refuses to download missing assets.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DECK_ID = "word-memory-v2"
TITLE = "英语谐音记忆词卡"
SOURCE = ROOT / "word-memory-app-v2.0.html"


def read_words():
    text = SOURCE.read_text(encoding="utf-8")
    match = re.search(r"\bvar\s+ALL_WORDS\s*=\s*", text)
    if not match:
        raise ValueError("Source has no ALL_WORDS array")
    words, _ = json.JSONDecoder().raw_decode(text[match.end():])
    required = ("word", "meaning", "pronunciation", "homophone", "memory_phrase")
    for index, item in enumerate(words, 1):
        if not all(isinstance(item.get(key), str) and item[key].strip() for key in required):
            raise ValueError(f"Invalid source entry {index}")
    return words


def audio_name(index, word):
    slug = re.sub(r"[^a-z0-9]+", "-", word.lower()).strip("-")
    return f"{index:04d}-{slug}.mp3"


def is_mp3(data):
    # Reject HTML/JSON error pages even when the server responds with HTTP 200.
    return len(data) > 256 and (data.startswith(b"ID3") or (data[0] == 255 and data[1] & 224 == 224))


def normalize_audio(data):
    if is_mp3(data):
        return data
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        # Youdao sometimes labels PCM WAV as audio/mpeg. Convert, never merely rename.
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                                 "-ac", "1", "-ar", "22050", "-codec:a", "libmp3lame",
                                 "-b:a", "48k", "-f", "mp3", "pipe:1"],
                                input=data, capture_output=True, check=True, timeout=30)
        if is_mp3(result.stdout):
            return result.stdout
    raise ValueError("Response is neither a valid MP3 nor a supported WAV")


def synthesize(word):
    if os.name != "nt":
        raise RuntimeError("The optional speech fallback requires Windows System.Speech")
    with tempfile.TemporaryDirectory(prefix="word-memory-") as folder:
        wav = Path(folder) / "speech.wav"
        command = """$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$wordVoice = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $wordVoice.SelectVoice('Microsoft Zira Desktop')
  $wordVoice.SetOutputToWaveFile($env:WORD_MEMORY_WAV)
  $wordVoice.Speak($env:WORD_MEMORY_TEXT)
} finally { $wordVoice.Dispose() }
"""
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                       env={**os.environ, "WORD_MEMORY_TEXT": word, "WORD_MEMORY_WAV": str(wav)},
                       capture_output=True, check=True, timeout=30)
        return normalize_audio(wav.read_bytes())


def cache_audio(index, item, offline, tts_fallback, previous):
    name = audio_name(index, item["word"])
    path = ROOT / "audio" / DECK_ID / name
    url = "https://dict.youdao.com/dictvoice?type=1&audio=" + quote(item["word"], safe="")
    kind = "youdao-uk"
    data = path.read_bytes() if path.exists() else b""
    if is_mp3(data) and previous and previous["sha256"] == hashlib.sha256(data).hexdigest():
        return previous
    if not is_mp3(data):
        if offline:
            raise ValueError(f"Missing or invalid audio: {name}")
        failure = None
        for voice_type in (1, 2):
            url = "https://dict.youdao.com/dictvoice?type=" + str(voice_type) + "&audio=" + quote(item["word"], safe="")
            for attempt in range(3):
                try:
                    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as response:
                        if "audio/" not in response.headers.get("Content-Type", ""):
                            raise ValueError(f"Not an audio response for {item['word']}")
                        data = normalize_audio(response.read())
                    kind = "youdao-uk" if voice_type == 1 else "youdao-us"
                    failure = None
                    break
                except Exception as exc:
                    failure = exc
                    if attempt < 2:
                        time.sleep(1 + attempt)
            if failure is None:
                break
        if failure is not None:
            if not tts_fallback:
                raise failure
            data = synthesize(item["word"])
            url, kind = None, "synthetic-en-us"
        temporary = path.with_suffix(".mp3.part")
        temporary.write_bytes(data)
        temporary.replace(path)
    return {"word": item["word"], "file": f"audio/{DECK_ID}/{name}",
            "sourceUrl": url, "kind": kind,
            "voice": "Microsoft Zira Desktop" if kind == "synthetic-en-us" else None,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--tts-fallback", action="store_true", help="Use labelled Windows English TTS if both Youdao voices fail")
    parser.add_argument("--workers", type=int, default=6, choices=range(1, 9))
    args = parser.parse_args()
    words = read_words()
    (ROOT / "audio" / DECK_ID).mkdir(parents=True, exist_ok=True)
    assets = [None] * len(words)
    failures = []
    manifest_path = ROOT / "outputs" / "word-memory-audio-manifest.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"assets": []}
    previous_assets = {Path(asset["file"]).name: asset for asset in previous["assets"]}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(cache_audio, i, word, args.offline, args.tts_fallback,
                            previous_assets.get(audio_name(i, word["word"]))): i for i, word in enumerate(words, 1)}
        for done, future in enumerate(as_completed(jobs), 1):
            index = jobs[future]
            try:
                assets[index - 1] = future.result()
            except Exception as exc:
                failures.append({"entry": index, "word": words[index - 1]["word"], "error": str(exc)})
            if done % 200 == 0 or done == len(words):
                print(f"Audio {done}/{len(words)}; failures: {len(failures)}", flush=True)
    write_json(ROOT / "outputs" / "word-memory-audio-failures.json", failures)
    completed = [asset for asset in assets if asset]
    write_json(manifest_path, {
        "source": SOURCE.name, "sourceSha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "cardCount": len(words), "audioCount": len(completed), "audioBytes": sum(a["bytes"] for a in completed),
        "pronunciation": "Youdao UK; labelled US or synthesized fallback when unavailable; punctuation preserved",
        "assets": completed})
    if failures:
        raise SystemExit("Audio incomplete; see outputs/word-memory-audio-failures.json. Rerun to retry.")

    letters = sorted({word["word"][0].lower() for word in words})
    cards = []
    for index, (word, asset) in enumerate(zip(words, assets), 1):
        audio = "./" + asset["file"]
        cards.append({
            "id": f"word-memory-{index:04d}", "type": "bilingual-basic", "status": "published",
            "categoryId": "letter-" + word["word"][0].lower(),
            "front": {"primary": word["word"], "phonetic": word["pronunciation"], "audio": audio},
            "back": {"primary": word["word"], "translation": word["meaning"],
                     "phonetic": word["pronunciation"], "homophone": word["homophone"],
                     "explanation": word["memory_phrase"], "audio": audio},
            "tags": ["英语词汇", "谐音记忆"],
            "source": {"type": "curated", "documentId": SOURCE.name, "locator": f"ALL_WORDS[{index - 1}]"},
            "generation": {"method": "import"},
        })
        label = {"youdao-uk": "英式发音", "youdao-us": "美式发音", "synthetic-en-us": "合成发音"}[asset["kind"]]
        for side in ("front", "back"):
            cards[-1][side]["audioLabel"] = label
    # Sort display order only. IDs, source locators and audio filenames retain
    # their original source indices so existing learning profiles still match.
    cards.sort(key=lambda card: (card["front"]["primary"].casefold(), card["id"]))
    deck = {
        "schemaVersion": "kdf/1.0",
        "deck": {"id": DECK_ID, "title": TITLE, "version": "2.0.3", "defaultCardType": "bilingual-basic",
                 "description": f"{len(words):,} 个词条 · 音标、中文释义、谐音与记忆句 · 点击播放离线发音",
                 "locale": "zh-CN", "theme": {"accent": "#533483"},
                 "learningMode": {"autoplayAudio": False, "answerReveal": "tap", "showSource": False}},
        "categories": [{"id": "letter-" + letter, "name": letter.upper(), "label": letter.upper() + " 开头",
                        "parentId": None, "sortOrder": i} for i, letter in enumerate(letters)],
        "cards": cards,
    }
    write_json(ROOT / "decks" / DECK_ID / "deck.json", deck)
    script = "window.__KDF_DECKS__ = window.__KDF_DECKS__ || {};\n"
    script += f"window.__KDF_DECKS__[{json.dumps(DECK_ID)}] = " + json.dumps(deck, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (ROOT / "data" / f"{DECK_ID}.js").write_text(script, encoding="utf-8")
    catalog_path = ROOT / "deck-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["decks"] = [entry for entry in catalog["decks"] if entry["id"] != DECK_ID]
    catalog["decks"].append({"id": DECK_ID, "title": TITLE, "path": f"./decks/{DECK_ID}/deck.json", "featured": True})
    write_json(catalog_path, catalog)
    # The actual offline learner loads classic scripts, not the JSON catalog.
    runtime = dict(catalog, decks=[{**{k: v for k, v in entry.items() if k != "path"},
                                  "script": f"./data/{entry['id']}.js"} for entry in catalog["decks"]])
    for entry in runtime["decks"]:
        if entry["id"] == DECK_ID:
            entry["script"] += "?v=" + deck["deck"]["version"]
    (ROOT / "data" / "catalog.js").write_text("window.__KDF_CATALOG__ = " + json.dumps(runtime, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    print(f"Created {len(cards)} cards and {len(assets)} local MP3 files.", flush=True)


if __name__ == "__main__":
    main()
