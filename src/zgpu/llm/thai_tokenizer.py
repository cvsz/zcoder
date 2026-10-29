"""Thai and Multilingual Unicode Tokenizer for zGPU LLM Engine.

Provides UTF-8 / Thai Unicode codepoint mapping (0x0E00 - 0x0E7F)
and standard ASCII/Latin characters directly into zGPU embedding indices.
"""

from __future__ import annotations

from typing import ClassVar


class ThaiMultilingualTokenizer:
    """Specialized UTF-8 character and subword tokenizer supporting Thai (ภาษาไทย) and ASCII."""

    # Special tokens
    PAD_TOKEN = 0
    BOS_TOKEN = 1
    EOS_TOKEN = 2
    UNK_TOKEN = 3

    # Common Thai vocabulary syllables / words for richer tokenization
    COMMON_THAI_WORDS: ClassVar[list[str]] = [
        "สวัสดี",
        "ครับ",
        "ค่ะ",
        "ขอบคุณ",
        "สบายดี",
        "ปัญญาประดิษฐ์",
        "คอมพิวเตอร์",
        "ระบบ",
        "ทำงาน",
        "ข้อมูล",
        "การ",
        "ความ",
        "ที่",
        "และ",
        "ใน",
        "ได้",
        "มี",
        "เป็น",
        "ให้",
        "ไม่",
    ]

    def __init__(self, vocab_size: int = 512):
        self.vocab_size = vocab_size
        self.token2id: dict[str, int] = {
            "<pad>": self.PAD_TOKEN,
            "<bos>": self.BOS_TOKEN,
            "<eos>": self.EOS_TOKEN,
            "<unk>": self.UNK_TOKEN,
        }
        self.id2token: dict[int, str] = {v: k for k, v in self.token2id.items()}

        next_id = 4

        # 1. Add common Thai words first
        for word in self.COMMON_THAI_WORDS:
            if next_id < self.vocab_size and word not in self.token2id:
                self.token2id[word] = next_id
                self.id2token[next_id] = word
                next_id += 1

        # 2. Add Printable ASCII (32 to 126)
        for code in range(32, 127):
            ch = chr(code)
            if next_id < self.vocab_size and ch not in self.token2id:
                self.token2id[ch] = next_id
                self.id2token[next_id] = ch
                next_id += 1

        # 3. Add Thai Unicode characters (0x0E01 ก to 0x0E5B ๛)
        for code in range(0x0E01, 0x0E5C):
            ch = chr(code)
            if next_id < self.vocab_size and ch not in self.token2id:
                self.token2id[ch] = next_id
                self.id2token[next_id] = ch
                next_id += 1

    def encode(self, text: str) -> list[int]:
        """Encode UTF-8 text containing English or Thai into token IDs."""
        tokens: list[int] = []
        i = 0
        n = len(text)

        while i < n:
            matched = False
            # Check for multi-character Thai word match
            for word in self.COMMON_THAI_WORDS:
                if text.startswith(word, i):
                    tokens.append(self.token2id[word])
                    i += len(word)
                    matched = True
                    break

            if not matched:
                ch = text[i]
                if ch in self.token2id:
                    tokens.append(self.token2id[ch])
                else:
                    # Fallback hash to vocab space
                    tokens.append((ord(ch) % (self.vocab_size - 4)) + 4)
                i += 1

        return tokens

    def decode(self, token_ids: list[int]) -> str:
        """Decode token IDs back to a readable string (English & Thai)."""
        result: list[str] = []
        for tid in token_ids:
            if tid in (self.PAD_TOKEN, self.BOS_TOKEN, self.EOS_TOKEN):
                continue
            if tid in self.id2token:
                result.append(self.id2token[tid])
            else:
                # If outside mapped tokens, fallback to modulo character
                result.append(chr(32 + (tid % 95)))
        return "".join(result)
