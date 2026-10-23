def _quoted(line: str, start: int) -> tuple[str, int]:
    out, i = [], start + 1
    while True:
        end = line.find('"', i)
        if end < 0:
            raise ValueError(f"unclosed quote at {start}")
        out.append(line[i:end])
        if line.startswith('""', end):
            out.append('"')
            i = end + 2
            continue
        return "".join(out), end + 1


def split_line(line: str) -> list[str]:
    fields: list[str] = []
    i = 0
    while True:
        if line.startswith('"', i):
            field, i = _quoted(line, i)
            while line.startswith(" ", i):
                i += 1
            if i < len(line) and line[i] != ",":
                raise ValueError(f"text after closing quote at {i}")
        else:
            comma = line.find(",", i)
            end = len(line) if comma < 0 else comma
            field, i = line[i:end], end
        fields.append(field)
        if i >= len(line):
            return fields
        i += 1
