from colorgame.automation import (
    BoardSignature,
    ClickDecision,
    board_has_changed,
    decide_click_action,
)


def sig(
    *,
    rows=6,
    cols=6,
    target_row=1,
    target_col=2,
    common_rgb=(205, 184, 75),
    target_rgb=(204, 180, 74),
):
    return BoardSignature(
        rows=rows,
        cols=cols,
        target_row=target_row,
        target_col=target_col,
        common_rgb=common_rgb,
        target_rgb=target_rgb,
    )


def test_same_board_is_not_changed():
    assert not board_has_changed(sig(), sig())


def test_target_position_change_is_new_level():
    assert board_has_changed(sig(), sig(target_col=4))


def test_color_change_is_new_level():
    assert board_has_changed(sig(), sig(common_rgb=(220, 184, 75)))


def test_tiny_capture_noise_is_ignored():
    assert not board_has_changed(
        sig(),
        sig(common_rgb=(207, 184, 75), target_rgb=(205, 181, 74)),
    )


def test_changed_board_always_advances():
    assert (
        decide_click_action(
            board_changed=True,
            click_number=1,
            poll_count=0,
            max_polls=12,
        )
        is ClickDecision.NEXT_LEVEL
    )


def test_unchanged_board_waits_before_deadline():
    assert (
        decide_click_action(
            board_changed=False,
            click_number=1,
            poll_count=4,
            max_polls=12,
        )
        is ClickDecision.WAIT
    )


def test_first_click_retries_once_at_deadline():
    assert (
        decide_click_action(
            board_changed=False,
            click_number=1,
            poll_count=12,
            max_polls=12,
        )
        is ClickDecision.RETRY
    )


def test_second_click_stops_at_deadline():
    assert (
        decide_click_action(
            board_changed=False,
            click_number=2,
            poll_count=12,
            max_polls=12,
        )
        is ClickDecision.STOP
    )
