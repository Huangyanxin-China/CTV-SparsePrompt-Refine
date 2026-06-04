import numpy as np
from scipy import ndimage


def dice_score(pred, gt):
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    return (2.0 * np.logical_and(pred, gt).sum() + 1e-6) / (pred.sum() + gt.sum() + 1e-6)


def surface_distances(pred, gt, spacing_zyx=(1.0, 1.0, 1.0)):
    pred = pred.astype(bool)
    gt = gt.astype(bool)
    if not pred.any() or not gt.any():
        return None
    structure = ndimage.generate_binary_structure(3, 1)
    pred_surface = pred ^ ndimage.binary_erosion(pred, structure=structure, border_value=0)
    gt_surface = gt ^ ndimage.binary_erosion(gt, structure=structure, border_value=0)
    dt_pred = ndimage.distance_transform_edt(~pred_surface, sampling=spacing_zyx)
    dt_gt = ndimage.distance_transform_edt(~gt_surface, sampling=spacing_zyx)
    return np.concatenate([dt_gt[pred_surface], dt_pred[gt_surface]])


def hd95_asd(pred, gt, spacing_xyz=(1.0, 1.0, 1.0)):
    spacing_zyx = tuple(float(v) for v in spacing_xyz[::-1])
    sd = surface_distances(pred, gt, spacing_zyx=spacing_zyx)
    if sd is None:
        return float("inf"), float("inf")
    return float(np.percentile(sd, 95)), float(sd.mean())
