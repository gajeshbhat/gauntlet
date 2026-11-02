from gauntlet.diagram import render


def test_layers_and_inward_edges() -> None:
    text = render(("web", "service", "domain"), frozenset({(0, 1), (0, 2), (1, 2)}))
    assert text == (
        'flowchart TD\n  L0["web"]\n  L1["service"]\n  L2["domain"]\n  L0 --> L1\n  L0 --> L2\n  L1 --> L2\n'
    )


def test_outward_edges_are_violations_drawn_dashed_and_red() -> None:
    text = render(("web", "domain"), frozenset({(0, 1), (1, 0)}))
    assert "  L0 --> L1\n" in text
    assert "  L1 -.->|violation| L0\n" in text
    assert text.endswith("  linkStyle 1 stroke:#d33,stroke-width:3px\n")


def test_several_violations_each_get_a_style() -> None:
    text = render(("a", "b", "c"), frozenset({(1, 0), (2, 0), (2, 1)}))
    assert text.count("linkStyle") == 3
    assert "  linkStyle 0 stroke:#d33,stroke-width:3px\n" in text
    assert "  linkStyle 2 stroke:#d33,stroke-width:3px\n" in text


def test_quotes_in_names_cannot_break_the_diagram() -> None:
    assert 'L0["a\'b"]' in render(('a"b',), frozenset())


def test_no_edges() -> None:
    assert render(("only",), frozenset()) == 'flowchart TD\n  L0["only"]\n'
