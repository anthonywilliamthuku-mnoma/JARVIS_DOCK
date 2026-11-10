from leond.dock import (
    COLLAPSED_H,
    EXPANDED_H,
    EXPANDED_W,
    TOP_MARGIN,
    WIDTH,
    geometry,
)


def test_the_dock_is_exactly_the_requested_size() -> None:
    assert (WIDTH, COLLAPSED_H) == (223, 43)


def test_collapsed_dock_is_centred_and_flush_with_the_top() -> None:
    x, y, width, height = geometry(1366, opened=False)
    assert (width, height) == (223, 43)
    assert x == (1366 - 223) // 2
    assert y == 0
    assert TOP_MARGIN == 0


def test_opening_grows_downwards_from_the_same_edge() -> None:
    x, y, width, height = geometry(1366, opened=True)
    assert (width, height) == (EXPANDED_W, EXPANDED_H)
    assert y == 0
    assert x == (1366 - EXPANDED_W) // 2


def test_both_states_share_the_same_centre_line() -> None:
    # Whole pixels: an odd width cannot land exactly on an even one's centre,
    # so the dock may shift by at most half a pixel when it opens.
    collapsed = geometry(1920, opened=False)
    opened = geometry(1920, opened=True)
    assert abs((collapsed[0] + collapsed[2] / 2) - (opened[0] + opened[2] / 2)) <= 0.5


def test_a_narrow_screen_is_not_overrun() -> None:
    x, _, width, _ = geometry(200, opened=False)
    assert x >= 0
    assert width <= 200
