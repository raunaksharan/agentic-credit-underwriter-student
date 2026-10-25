"""Spec for rrf_merge (lesson 2 exercise: make these pass)."""

import pytest

from underwriter.rag.fusion import rrf_merge


def test_item_in_both_lists_wins():
    merged = rrf_merge([["a", "b", "c"], ["b", "d"]], k=60)
    assert merged[0][0] == "b"


def test_scores_follow_formula():
    merged = dict(rrf_merge([["a", "b"], ["b", "c"]], k=0))
    assert merged == {"a": 1.0, "b": 1.5, "c": 0.5}


def test_ties_break_by_first_appearance():
    assert [i for i, _ in rrf_merge([["x"], ["y"]])] == ["x", "y"]


def test_duplicates_within_a_list_count_once():
    assert dict(rrf_merge([["a", "a"]], k=0)) == {"a": 1.0}


def test_empty_inputs():
    assert rrf_merge([]) == []
    assert rrf_merge([[], []]) == []


def test_negative_k_rejected():
    with pytest.raises(ValueError):
        rrf_merge([["a"]], k=-1)
