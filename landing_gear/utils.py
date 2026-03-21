"""Miscellaneous helper functions can live here in later passes."""



def sanitize_log_value(value: object, *, max_len: int = 512) -> str:
    text = str(value)
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text
