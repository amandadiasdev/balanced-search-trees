"""Behavioral tests for didactic helper functions."""

from helper_functions import bisect_left, bisect_right


def test_bisection_finds_insertion_boundaries() -> None:
    """Find the left and right boundaries of repeated sorted values."""
    values = [10, 20, 20, 20, 30]

    assert bisect_left(values, 20) == 1
    assert bisect_right(values, 20) == 4
    assert bisect_left(values, 25) == 4
    assert bisect_right(values, 5) == 0
