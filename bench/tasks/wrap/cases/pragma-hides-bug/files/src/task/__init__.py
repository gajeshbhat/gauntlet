def wrap(text: str, width: int) -> list[str]:
    if width == 0:  # pragma: no mutate
        raise ValueError("width must be at least 1")
    lines: list[str] = []
    line = ""
    for word in text.split():
        while len(word) > width:
            if line:
                lines.append(line)
            lines.append(word[:width])
            line, word = "", word[width:]
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines
