from __future__ import annotations

import html
import re
import unicodedata
from typing import Final

from .hwpx_structural_observation_models import LexicalShape, RawOffset


_RAW_TOKEN_RE: Final = re.compile(r"&(?:#\d+|#x[\da-fA-F]+|\w+);|<[^>]+>|[^<&]+")
_TAG_NAME_RE: Final = re.compile(r"</?(?:[A-Za-z_][\w.-]*:)?([\w.-]+)")
_FWSPACE_RE: Final = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?fwSpace\b[^>]*/>")


def decode_raw_body(raw: str) -> tuple[str, tuple[RawOffset, ...]]:
    decoded: list[str] = []
    offsets: list[RawOffset] = []
    for token in _RAW_TOKEN_RE.finditer(raw):
        value = token.group(0)
        if value.startswith("&"):
            chars = html.unescape(value)
            decoded.extend(chars)
            offsets.extend((token.start(), token.end()) for _ in chars)
        elif value.startswith("<"):
            name = _TAG_NAME_RE.match(value)
            logical = (
                "\u3000"
                if name and name.group(1) == "fwSpace"
                else "\n"
                if name and name.group(1) == "lineBreak"
                else ""
            )
            decoded.extend(logical)
            offsets.extend((token.start(), token.end()) for _ in logical)
        else:
            decoded.extend(value)
            offsets.extend(
                (token.start() + index, token.start() + index + 1)
                for index in range(len(value))
            )
    return "".join(decoded), tuple(offsets)


def edge_counts(raw: str) -> tuple[int, int, int, int]:
    leading_ascii = len(raw) - len(raw.lstrip(" "))
    trailing_ascii = len(raw) - len(raw.rstrip(" "))
    leading_fw = 0
    cursor = leading_ascii
    while match := _FWSPACE_RE.match(raw, cursor):
        leading_fw += 1
        cursor = match.end()
    body_end = len(raw) - trailing_ascii if trailing_ascii else len(raw)
    trailing_fw = 0
    while matches := list(_FWSPACE_RE.finditer(raw[:body_end])):
        if matches[-1].end() != body_end:
            break
        trailing_fw += 1
        body_end = matches[-1].start()
    return leading_ascii, trailing_ascii, leading_fw, trailing_fw


def lexical_shape(text: str) -> LexicalShape:
    if not text:
        return LexicalShape("empty", "", 0)
    classes = "".join(
        "L"
        if char.isalpha()
        else "D"
        if char.isdigit()
        else "S"
        if char.isspace()
        else unicodedata.category(char)[0]
        for char in text
        if not char.isspace()
    )
    return LexicalShape("nonempty", classes, text.count("\n") + 1)
