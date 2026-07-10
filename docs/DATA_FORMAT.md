# Data and Geometry Contract

## Directory layout

The main training entry point expects nnU-Net-like folders:

```text
dataset/
  imagesTr/
    case_001_0000.nii.gz
  labelsTr/
    case_001.nii.gz
  imagesTs/
    case_101_0000.nii.gz
  labelsTs/
    case_101.nii.gz

oar_dataset/
  labelsTr/
    case_001.nii.gz
  labelsTs/
    case_101.nii.gz
```

## Coordinate system

For every case, CT, target label, OAR label, prompt, pseudo-label, and prediction must agree in:

- array size;
- voxel spacing;
- physical origin;
- direction cosine matrix.

Labels must be resampled with nearest-neighbor interpolation when alignment is required. Matching array shapes alone does not establish physical alignment.

## Label mapping

Do not assume that all non-zero voxels represent CTV or that a fixed numeric value always represents the spinal cord. Record the target and OAR label mapping for each dataset and pass explicit label values to data-preparation code.

## Sparse prompts

A prompt volume contains target masks only on annotated axial slices and background elsewhere. Prompt selection derived from complete labels is a retrospective simulation protocol, not a deployable annotation interface. Record the selected slice indices and strategy for every case.

## Privacy

Raw or reversible medical data must remain outside Git tracking. Sequential rendered slices can still disclose anatomy; obtain the appropriate release approval before publishing them.
