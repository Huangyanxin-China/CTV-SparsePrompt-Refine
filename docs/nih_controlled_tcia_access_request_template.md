# NIH Controlled TCIA Dataset Access Request Template

Datasets:

```text
GLIS-RT
TCIA DOI: https://doi.org/10.7937/TCIA.T905-ZQ20
TCIA page: https://www.cancerimagingarchive.net/collection/glis-rt/
Manifest accession: phs004225

Burdenko-GBM-Progression
TCIA DOI: https://doi.org/10.7937/E1QP-D183
TCIA page: https://www.cancerimagingarchive.net/collection/burdenko-gbm-progression/
```

## Project Title

```text
Sparse-prompted multimodal radiotherapy CTV completion using CT, MRI, RTSTRUCT contours, OAR constraints, and SDF core-envelope priors
```

## Research Use Statement

```text
We request controlled access to multimodal radiotherapy imaging datasets with CTV annotations to evaluate a sparse-prompted clinical target volume completion method. Our method uses a small number of 2D CTV annotations as sparse prompts, propagates them into a 3D candidate using signed distance functions, constructs a high-precision core and high-recall envelope, and performs anatomy-constrained refinement using CT/MRI and OAR information.

Our primary institutional thoracic CTV dataset cannot be publicly released due to patient privacy and institutional restrictions. The requested TCIA datasets provide external multimodal radiotherapy CTV validation data, including CT, MRI, image registrations, and RTSTRUCT target/OAR contours.
```

## Requested Data

```text
GLIS-RT:
    CT, MR, REG, RTSTRUCT
    230 subjects
    GTV/CTV/OAR contours

Burdenko-GBM-Progression:
    CT, multi-sequence MR, RTSTRUCT, RTPLAN, RTDOSE
    180 subjects
    GTV/CTV/PTV/OAR contours
```

## Planned Analysis

```text
1. Convert DICOM CT/MR and RTSTRUCT contours to NIfTI.
2. Register multimodal images where needed using provided REG objects or official processing code.
3. Simulate K=3/5/7 sparse CTV slice prompts from full CTV contours.
4. Run sparse prompt -> SDF propagation -> core-envelope construction.
5. Evaluate CTV completion against full physician CTV contours.
6. Compare CT-only, MR-only, and CT+MR multimodal variants when geometry supports it.
7. Report aggregate segmentation metrics only.
```

## Data Security

```text
Data will be stored on an access-controlled institutional server. Raw DICOM files, RTSTRUCT files, and derived subject-level NIfTI data will not be redistributed. Public release will be limited to code, aggregate metrics, and non-identifying results permitted under the data-use terms.
```

## Local Preparation Already Completed

```text
GLIS-RT manifests:
    public_data/glis_rt/GC_manifest_GLIS-RT_20260326.csv
    public_data/glis_rt/manifests/

Burdenko manifests:
    public_data/burdenko_gbm_progression/GC_manifest_Burdenko-GBM-Progression_20260326.csv
    public_data/burdenko_gbm_progression/manifests/

Download helper:
    scripts/download_gen3_drs_manifest.sh
```

After credentials are available:

```bash
export GEN3_CREDENTIALS_JSON=/path/to/credentials.json

bash scripts/download_gen3_drs_manifest.sh \
  public_data/glis_rt/manifests/glis_rt_all_gen3_manifest.json \
  public_data/glis_rt/raw_zips

bash scripts/download_gen3_drs_manifest.sh \
  public_data/burdenko_gbm_progression/manifests/burdenko_gbm_all_gen3_manifest.json \
  public_data/burdenko_gbm_progression/raw_zips
```
