import numpy as np
import pytest

from run_traditional_linear_mask_interpolation_baseline import (
    linear_mask_interpolation,
)
from utils.metrics import dice_score, hd95_asd
from utils.rules import extract_threshold_rule, threshold_condition


def test_linear_interpolation_preserves_prompts_without_extrapolation():
    prompt = np.zeros((5, 5, 5), dtype=bool)
    prompt[1, 1:4, 1:4] = True
    prompt[3, 1:4, 1:4] = True

    result = linear_mask_interpolation(prompt)

    np.testing.assert_array_equal(result[1], prompt[1])
    np.testing.assert_array_equal(result[2], prompt[1])
    np.testing.assert_array_equal(result[3], prompt[3])
    assert not result[0].any()
    assert not result[4].any()


def test_threshold_ge_includes_equal_value():
    assert threshold_condition(2.0, "ge", 2.0)
    assert not threshold_condition(1.999, "ge", 2.0)
    assert threshold_condition(1.999, "lt", 2.0)


def test_invalid_threshold_operator_is_rejected():
    with pytest.raises(ValueError, match="Unsupported threshold operator"):
        threshold_condition(2.0, "gt", 2.0)


def test_threshold_rule_can_be_loaded_from_screen_summary():
    rule = {
        "feature": "core_base_vol_ratio",
        "op": "ge",
        "threshold": 1.0,
        "method_if_true": "support_100",
        "method_if_false": "linear",
    }
    assert extract_threshold_rule({"threshold_rule": rule}) == rule


def test_identical_masks_have_unit_dice():
    mask = np.zeros((5, 5, 5), dtype=bool)
    mask[2, 2, 2] = True
    assert dice_score(mask, mask) == pytest.approx(1.0)


def test_surface_distance_respects_physical_spacing():
    pred = np.zeros((5, 5, 5), dtype=bool)
    gt = np.zeros_like(pred)
    pred[1, 2, 2] = True
    gt[2, 2, 2] = True

    hd95, asd = hd95_asd(pred, gt, spacing_xyz=(2.0, 3.0, 4.0))

    assert hd95 == pytest.approx(4.0)
    assert asd == pytest.approx(4.0)
