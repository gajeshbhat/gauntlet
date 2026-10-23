def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    for start, end in intervals:
        if start > end:
            raise ValueError(f"start after end: ({start}, {end})")
    merged: list[tuple[int, int]] = []
    intervals.sort()
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
