"""Behavioral tests for the augmented AVL tree."""

from bisect import bisect_left, bisect_right
from random import Random

from augmented_avl import AugmentedAVLTree


def test_tree_starts_empty_and_inserts_root() -> None:
    """Insert the first key with complete leaf metadata and no parent."""
    tree = AugmentedAVLTree()

    assert len(tree) == 0
    assert tree.insert(20) is True
    assert len(tree) == 1
    assert tree.root is not None
    assert tree.root.key == 20
    assert tree.root.parent is None
    assert tree.root.height == 1
    assert tree.root.size == 1
    assert tree.root.subtree_max == 20


def test_sorted_insertion_rebalances_and_preserves_parent_links() -> None:
    """Rotate a sorted insertion while preserving links and metadata."""
    tree = AugmentedAVLTree()

    assert [tree.insert(key) for key in (10, 20, 30)] == [True, True, True]
    assert tree.root is not None
    assert tree.root.key == 20
    assert tree.root.parent is None
    assert tree.root.left is not None
    assert tree.root.left.key == 10
    assert tree.root.left.parent is tree.root
    assert tree.root.right is not None
    assert tree.root.right.key == 30
    assert tree.root.right.parent is tree.root
    assert tree.root.height == 2
    assert tree.root.size == 3
    assert tree.root.subtree_max == 30
    assert tree.rotation_count == 1
    tree.assert_valid()


def test_search_and_duplicate_insert_observe_set_semantics() -> None:
    """Search existing and absent keys while treating duplicates as no-ops."""
    tree = AugmentedAVLTree()
    for key in (40, 20, 60, 10, 30, 50, 70):
        tree.insert(key)

    assert tree.insert(30) is False
    assert len(tree) == 7
    assert tree.search(10) is True
    assert tree.search(40) is True
    assert tree.search(99) is False
    tree.assert_valid()


def test_delete_handles_leaf_one_child_two_children_and_absent_key() -> None:
    """Delete every structural case without breaking AVL invariants."""
    tree = AugmentedAVLTree()
    for key in (40, 20, 60, 10, 30, 50, 70, 55):
        tree.insert(key)

    for key in (10, 50, 60, 40):
        assert tree.delete(key) is True
        assert tree.search(key) is False
        tree.assert_valid()

    assert tree.delete(999) is False
    assert len(tree) == 4
    assert tree.root is not None
    assert tree.root.parent is None
    tree.assert_valid()


def test_rank_and_select_use_zero_based_order_statistics() -> None:
    """Query positions through the public order-statistics interface."""
    tree = AugmentedAVLTree()
    for key in (40, 20, 60, 10, 30, 50, 70):
        tree.insert(key)

    assert [tree.rank(key) for key in (5, 10, 35, 40, 99)] == [0, 0, 3, 3, 7]
    assert [tree.select(index) for index in range(len(tree))] == [10, 20, 30, 40, 50, 60, 70]

    for index in (-1, len(tree)):
        try:
            tree.select(index)
        except IndexError:
            pass
        else:
            raise AssertionError(f"select({index}) should raise IndexError")


def test_range_agg_returns_maximum_in_closed_interval() -> None:
    """Return the greatest stored key inside an inclusive interval."""
    tree = AugmentedAVLTree()
    for key in (40, 20, 60, 10, 30, 50, 70):
        tree.insert(key)

    assert tree.range_agg(20, 60) == 60
    assert tree.range_agg(21, 59) == 50
    assert tree.range_agg(30, 30) == 30
    assert tree.range_agg(31, 39) is None
    assert tree.range_agg(71, 90) is None

    try:
        tree.range_agg(60, 20)
    except ValueError:
        pass
    else:
        raise AssertionError("an inverted interval should raise ValueError")


def test_all_insertion_rotation_patterns_preserve_the_same_order() -> None:
    """Exercise LL, RR, LR, and RL balancing through public insertions."""
    for sequence in ((30, 20, 10), (10, 20, 30), (30, 10, 20), (10, 30, 20)):
        tree = AugmentedAVLTree()
        for key in sequence:
            tree.insert(key)

        assert tree.root is not None
        assert tree.root.key == 20
        assert [tree.select(index) for index in range(len(tree))] == [10, 20, 30]
        tree.assert_valid()


def test_sorted_insertion_remains_iterative_at_ten_thousand_keys() -> None:
    """Process the pathological insertion order without recursive operations."""
    tree = AugmentedAVLTree()

    for key in range(10_000):
        tree.insert(key)

    assert len(tree) == 10_000
    assert tree.select(0) == 0
    assert tree.select(9_999) == 9_999
    assert tree.root is not None
    assert tree.root.height < 20
    tree.assert_valid()


def test_random_mutations_match_an_independent_sorted_reference() -> None:
    """Compare every public result with a set and sorted-list reference."""
    random = Random(5)
    tree = AugmentedAVLTree()
    reference: set[int] = set()

    for _ in range(1_000):
        key = random.randrange(250)
        if random.random() < 0.55:
            expected = key not in reference
            assert tree.insert(key) is expected
            reference.add(key)
        else:
            expected = key in reference
            assert tree.delete(key) is expected
            reference.discard(key)

        ordered = sorted(reference)
        query = random.randrange(300)
        lower, upper = sorted((random.randrange(300), random.randrange(300)))
        start = bisect_left(ordered, lower)
        end = bisect_right(ordered, upper)
        expected_range = ordered[end - 1] if start < end else None

        assert len(tree) == len(ordered)
        assert tree.search(query) is (query in reference)
        assert tree.rank(query) == bisect_left(ordered, query)
        assert tree.range_agg(lower, upper) == expected_range
        if ordered:
            index = random.randrange(len(ordered))
            assert tree.select(index) == ordered[index]
        tree.assert_valid()
