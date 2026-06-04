import os

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
    sitk.WriteImage(image, path)


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
