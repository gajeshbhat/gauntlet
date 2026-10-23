import pytest

from task import split_amount


@pytest.mark.parametrize(
    ("cents", "weights", "parts"),
    [
        (100, [1, 1], [50, 50]),
        (100, [1, 1, 1], [34, 33, 33]),
        (100, [1, 2], [33, 67]),
        (10, [1, 0, 1], [5, 0, 5]),
        (0, [1, 1], [0, 0]),
        (7, [5], [7]),
        (5, [1, 1, 1, 1], [2, 1, 1, 1]),
    ],
)
def test_parts_add_up_and_follow_the_weights(cents: int, weights: list[int], parts: list[int]) -> None:
    assert split_amount(cents, weights) == parts


@pytest.mark.parametrize(
    ("cents", "weights", "message"),
    [
        (-1, [1], "cents must not be negative"),
        (1, [], "weights must not be empty"),
        (1, [1, -2], "weights must not be negative"),
        (1, [0, 0], "weights must not all be zero"),
    ],
)
def test_bad_input_is_named(cents: int, weights: list[int], message: str) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        split_amount(cents, weights)
