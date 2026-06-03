"""Tokenizer for PR review text — Chinese + English + code identifiers.

Uses jieba for Chinese segmentation with custom dictionary.
English/code tokens are extracted by regex pattern.
"""
from __future__ import annotations

import os
import re

try:
    import jieba
    jieba.setLogLevel(20)
    _dict_path = os.path.join(os.path.dirname(__file__), "custom_dict.txt")
    if os.path.exists(_dict_path):
        jieba.load_userdict(_dict_path)
except ImportError:
    jieba = None


def tokenize(text: str) -> list[str]:
    """Tokenize text into a list of tokens.

    - English/code identifiers: matched by regex [a-zA-Z_][a-zA-Z0-9_]*
    - Chinese text: segmented by jieba
    - Single-character tokens are filtered out

    Args:
        text: Input text (mixed Chinese/English/code)

    Returns:
        List of tokens (lowercase, length > 1)
    """
    text = text.lower()
    tokens = []
    for seg in re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*|[一-鿿]+', text):
        if seg[0].isascii():
            tokens.append(seg)
        elif jieba is not None:
            tokens.extend(jieba.cut(seg))
        else:
            tokens.append(seg)
    return [t for t in tokens if len(t) > 1]
