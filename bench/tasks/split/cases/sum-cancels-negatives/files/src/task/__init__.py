def split_amount(cents: int, weights: list[int]) -> list[int]:
    if cents < 0:
        raise ValueError("cents must not be negative")
    if not weights:
        raise ValueError("weights must not be empty")
    if sum(weights) < 0:
        raise ValueError("weights must not be negative")
    total = sum(weights)
    if total == 0:
        raise ValueError("weights must not all be zero")
    parts = [cents * w // total for w in weights]
    remainders = [cents * w % total for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for i in order[: cents - sum(parts)]:
        parts[i] += 1
    return parts
