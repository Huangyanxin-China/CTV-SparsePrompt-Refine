import os

import numpy as np
import SimpleITK as sitk


def ensure_dir(path):
    if not path:
        return
    os.makedirs(path, exist_ok=True)


def read_image(path):
    image = sitk.ReadImage(path)
    array = sitk.GetArrayFromImage(image)
    return array, image


def write_like(array, reference, path, dtype=None):
    ensure_dir(os.path.dirname(path))
    out = array.astype(dtype) if dtype is not None else array
    image = sitk.GetImageFromArray(out)
    image.CopyInformation(reference)
    sitk.WriteImage(image, path, useCompression=True)


def geometry_differences(reference, candidate, atol=1e-5):
    """Return physical-geometry fields that differ between two SITK images."""
    differences = {}
    if tuple(reference.GetSize()) != tuple(candidate.GetSize()):
        differences["size"] = {
            "reference": tuple(int(v) for v in reference.GetSize()),
            "candidate": tuple(int(v) for v in candidate.GetSize()),
        }

    fields = {
        "spacing": (reference.GetSpacing(), candidate.GetSpacing()),
        "origin": (reference.GetOrigin(), candidate.GetOrigin()),
        "direction": (reference.GetDirection(), candidate.GetDirection()),
    }
    for name, (expected, observed) in fields.items():
        expected_arr = np.asarray(expected, dtype=float)
        observed_arr = np.asarray(observed, dtype=float)
        if not np.allclose(expected_arr, observed_arr, rtol=0.0, atol=float(atol)):
            differences[name] = {
                "reference": tuple(float(v) for v in expected_arr),
                "candidate": tuple(float(v) for v in observed_arr),
            }
    return differences


def assert_same_geometry(reference, candidate, reference_name="reference", candidate_name="candidate", atol=1e-5):
    """Raise when two medical images do not occupy the same physical grid."""
    differences = geometry_differences(reference, candidate, atol=atol)
    if differences:
        details = "; ".join(
            f"{field}: {values['reference']} != {values['candidate']}"
            for field, values in differences.items()
        )
        raise ValueError(
            f"Image geometry mismatch between {reference_name} and {candidate_name}: {details}"
        )


def resample_to_spacing(image, spacing=(1.0, 1.0, 1.0), is_label=False):
    spacing = tuple(float(v) for v in spacing)
    orig_spacing = image.GetSpacing()
    orig_size = image.GetSize()
    new_size = [
        int(round(orig_size[i] * (orig_spacing[i] / spacing[i])))
        for i in range(3)
    ]
    resampler = sitk.ResampleImageFilter()
    resampler.SetOutputSpacing(spacing)
    resampler.SetSize(new_size)
    resampler.SetOutputDirection(image.GetDirection())
    resampler.SetOutputOrigin(image.GetOrigin())
    resampler.SetInterpolator(sitk.sitkNearestNeighbor if is_label else sitk.sitkLinear)
    return resampler.Execute(image)
