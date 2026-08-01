from colorgame.automation import BoardSignature, board_has_changed


def signature(
    *,
    rows: int = 6,
    cols: int = 6,
    target_row: int = 1,
    target_col: int = 2,
    common_rgb: tuple[int, int, int] = (205, 184, 75),
    target_rgb: tuple[int, int, int] = (204, 180, 74),
) -> BoardSignature:
    return BoardSignature(rows, cols, target_row, target_col, common_rgb, target_rgb)


def test_same_board_is_not_changed() -> None:
    assert not board_has_changed(signature(), signature(common_rgb=(206, 184, 75)))


def test_new_target_means_board_changed() -> None:
    assert board_has_changed(signature(), signature(target_row=4, target_col=5))


def test_new_grid_size_means_board_changed() -> None:
    assert board_has_changed(signature(), signature(rows=7, cols=7))


def test_large_color_change_means_board_changed() -> None:
    assert board_has_changed(signature(), signature(common_rgb=(214, 191, 83)))
