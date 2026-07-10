import numpy as np
import pytest
import SimpleITK as sitk

import run_sparse_prompt_core_envelope_workflow as workflow
from utils.geometry import signed_distance
from utils.io import assert_same_geometry, geometry_differences


def test_signed_distance_has_expected_sign():
    mask = np.zeros((7, 7), dtype=bool)
    mask[2:5, 2:5] = True

    sdf = signed_distance(mask)

    assert sdf.dtype == np.float32
    assert np.all(sdf[mask] > 0)
    assert np.all(sdf[~mask] < 0)


def test_sparse_slice_selection_is_deterministic():
    gt = np.zeros((7, 5, 5), dtype=bool)
    gt[1:6, 1:4, 1:4] = True

    selected = workflow.select_sparse_slices(
        gt, 3, "even_nonempty", "case_a"
    )
    assert selected.tolist() == [1, 3, 5]

    first = workflow.select_sparse_slices(
        gt, 3, "random_seeded", "case_a"
    )
    second = workflow.select_sparse_slices(
        gt, 3, "random_seeded", "case_a"
    )
    np.testing.assert_array_equal(first, second)


def test_unknown_prompt_strategy_is_rejected():
    gt = np.ones((5, 3, 3), dtype=bool)
    with pytest.raises(ValueError, match="Unknown prompt strategy"):
        workflow.select_sparse_slices(gt, 3, "unknown", "case")


def test_keep_seed_connected_removes_unseeded_component():
    mask = np.zeros((8, 8, 8), dtype=bool)
    mask[1:3, 1:3, 1:3] = True
    mask[5:7, 5:7, 5:7] = True
    seed = np.zeros_like(mask)
    seed[1, 1, 1] = True

    result = workflow.keep_seed_connected(mask, seed)

    assert result[1:3, 1:3, 1:3].all()
    assert not result[5:7, 5:7, 5:7].any()


def test_build_methods_preserves_prompt_and_constraints():
    prompt = np.zeros((7, 15, 15), dtype=bool)
    prompt[2, 5:10, 5:10] = True
    prompt[4, 5:10, 5:10] = True
    selected_z = np.array([2, 4])

    oar = np.zeros(prompt.shape, dtype=np.uint8)
    oar[3, 7, 7] = 9

    methods, support, n_candidates = workflow.build_methods(
        prompt,
        selected_z,
        (1.0, 1.0, 1.0),
        oar,
        "current",
        spinal_label=9,
    )

    core = methods["core_only"]
    envelope = methods["envelope"]
    assert np.all(core <= envelope)
    assert np.all(core[prompt])
    assert np.all(envelope[prompt])
    assert not envelope[3, 7, 7]
    assert np.all((support >= 0.0) & (support <= 1.0))
    assert n_candidates == len(workflow.profile_candidates("current"))


def test_image_geometry_checks_origin_direction_and_tolerance():
    reference = sitk.Image([5, 6, 7], sitk.sitkUInt8)
    candidate = sitk.Image([5, 6, 7], sitk.sitkUInt8)
    reference.SetSpacing((1.0, 1.0, 2.0))
    candidate.SetSpacing((1.0, 1.0, 2.0 + 1e-7))

    assert geometry_differences(reference, candidate, atol=1e-5) == {}
    assert_same_geometry(reference, candidate)

    candidate.SetOrigin((1.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="origin"):
        assert_same_geometry(reference, candidate)
