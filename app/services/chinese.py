from functools import lru_cache


@lru_cache(maxsize=1)
def _opencc_converter():
    try:
        from opencc import OpenCC
    except Exception:
        return None
    return OpenCC("t2s")


def to_simplified_chinese(text: str) -> str:
    if not text:
        return text
    converter = _opencc_converter()
    if converter is None:
        return text
    return converter.convert(text)
