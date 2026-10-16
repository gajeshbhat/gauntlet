"""Mermaid flowchart of the layer graph: inward dependencies solid, outward ones (violations) dashed and red."""


def _label(name: str) -> str:
    return name.replace('"', "'")


def render(layers: tuple[str, ...], edges: frozenset[tuple[int, int]]) -> str:
    lines = ["flowchart TD", *[f'  L{i}["{_label(name)}"]' for i, name in enumerate(layers)]]
    styles: list[str] = []
    for index, (src, dst) in enumerate(sorted(edges)):
        if dst < src:  # points at an outer layer
            lines.append(f"  L{src} -.->|violation| L{dst}")
            styles.append(f"  linkStyle {index} stroke:#d33,stroke-width:3px")
        else:
            lines.append(f"  L{src} --> L{dst}")
    return "\n".join([*lines, *styles]) + "\n"
