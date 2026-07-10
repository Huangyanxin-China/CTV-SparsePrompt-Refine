from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from train_ctv_pseudo_refine_net import (
    CasePaths,
    build_pseudo_features,
    load_rule,
    make_train_val_split,
)


def test_build_features_uses_named_rule_feature_and_ge_boundary():
    shape = (7, 15, 15)
    ct = np.zeros(shape, dtype=np.float32)
    gt = np.zeros(shape, dtype=bool)
    gt[1:6, 5:10, 5:10] = True
    oar = np.zeros(shape, dtype=np.uint8)
    image = sitk.GetImageFromArray(gt.astype(np.uint8))
    image.SetSpacing((1.0, 1.0, 2.0))

    rule = {
        "feature": "z_extent",
        "op": "ge",
        "threshold": 4.0,
        "method_if_true": "linear",
        "method_if_false": "support_100",
    }
    features = build_pseudo_features(
        ct=ct,
        gt=gt,
        gt_img=image,
        oar=oar,
        case_id="case_a",
        k=3,
        strategy="even_nonempty",
        pseudo_profile="current",
        refine_profile="high_recall",
        refine_mode="fast_margin",
        refine_margin_mm=10.0,
        anatomy_margin_mm=10.0,
        rule=rule,
    )

    assert features["rule_feature"] == pytest.approx(4.0)
    assert features["pseudo_method"] == "linear"


def test_explicit_missing_rule_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_rule(tmp_path / "missing-rule.json")


def test_train_validation_split_keeps_subject_scans_together():
    cases = [
        CasePaths("P001_CT1", "Tr", Path("a"), Path("b"), Path("c")),
        CasePaths("P001_CT2", "Tr", Path("d"), Path("e"), Path("f")),
        CasePaths("P002_CT1", "Tr", Path("g"), Path("h"), Path("i")),
        CasePaths("P003_CT1", "Tr", Path("j"), Path("k"), Path("l")),
    ]

    train, val = make_train_val_split(
        cases,
        val_fraction=0.34,
        seed=7,
        subject_separator="_CT",
    )
    train_subjects = {case.case_id.split("_CT", 1)[0] for case in train}
    val_subjects = {case.case_id.split("_CT", 1)[0] for case in val}

    assert train_subjects.isdisjoint(val_subjects)
    assert {case.case_id for case in train + val} == {
        case.case_id for case in cases
    }
