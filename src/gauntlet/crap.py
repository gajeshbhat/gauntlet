"""CRAP (Change Risk Anti-Patterns) score: complexity^2 * (1 - coverage)^3 + complexity."""


def crap_score(complexity: int, coverage: float) -> float:
    if not 0.0 <= coverage <= 1.0:
        raise ValueError(f"coverage must be within 0..1, got {coverage}")
    return complexity**2 * (1 - coverage) ** 3 + complexity
