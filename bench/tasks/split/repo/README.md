# Task: split an amount

Implement `task.split_amount(cents: int, weights: list[int]) -> list[int]` in `src/task/__init__.py`, and write tests
in `tests/`.

- Split `cents` (an amount of money, `>= 0`) into one part per weight, in proportion to the weights.
- The parts are whole cents and always add up to exactly `cents`.
- Each part starts at the floor of its exact share; cents still left over go one each to the parts with the
  largest remainders, ties going to the earlier part.
- Weights are `>= 0` and at least one is positive.
- Raise `ValueError` for negative `cents` (`cents must not be negative`), an empty or negative weight
  (`weights must not be negative`, `weights must not be empty`) or all-zero weights (`weights must not all be zero`).
