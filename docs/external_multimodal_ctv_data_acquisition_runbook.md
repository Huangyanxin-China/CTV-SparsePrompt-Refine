# External Multimodal CTV Data Acquisition Runbook

Date: 2026-05-31

## Decision

For the Pattern Recognition special issue on multimodal biomedical data, the project should not use MSD Task06 Lung as the external dataset. MSD is single-modal CT lesion segmentation and does not validate multimodal radiotherapy CTV delineation.

Use this priority order instead:

```text
1. SegRap2025 LNCTVSeg
   non-contrast CT + contrast-enhanced CT
   lymph-node CTV
   262 patients / 440 CT images
   2.15GB zip
   Downloaded and extracted

2. GLIS-RT
   CT + MR + REG + RTSTRUCT
   GTV/CTV/OAR
   230 subjects
   28.26GB
   Best stricter CT+MR external dataset after access approval

3. Burdenko-GBM-Progression
   CT + multi-sequence MR + RTSTRUCT + RTPLAN + RTDOSE
   GTV/CTV/PTV/OAR
   180 subjects
   131.23GB
   Stronger but larger second dataset

4. LUND-PROBE
   MRI + synthetic CT
   CTV/PTV/OAR/dose
   467 scans
   176.56GB
   Good prostate radiotherapy dataset, requires AIDA approval
```

## Current Local State

Public metadata and helper files are already on the server:

```text
public_data/segrap2025_lnctv/
public_data/glis_rt/
public_data/burdenko_gbm_progression/
public_data/lund_probe/
```

SegRap2025 LNCTVSeg is already downloaded:

```text
public_data/segrap2025_lnctv/extracted/LNCTVSeg-DataSet/
public_data/segrap2025_lnctv/segrap2025_lnctv_manifest.csv
public_data/segrap2025_lnctv/segrap2025_lnctv_summary.json
```

Verification:

```text
size: 2,151,914,296 bytes
md5: 5cb2ed3a1f57f43e849e19cf8c755169
raw zip status: removed on 2026-06-02 after verified extraction
NIfTI files: 844
```

Generated Gen3 manifests:

```text
public_data/glis_rt/manifests/glis_rt_all_gen3_manifest.json
public_data/glis_rt/manifests/glis_rt_ct_gen3_manifest.json
public_data/glis_rt/manifests/glis_rt_mr_gen3_manifest.json
public_data/glis_rt/manifests/glis_rt_rtstruct_gen3_manifest.json
public_data/glis_rt/manifests/glis_rt_reg_gen3_manifest.json

public_data/burdenko_gbm_progression/manifests/burdenko_gbm_all_gen3_manifest.json
public_data/burdenko_gbm_progression/manifests/burdenko_gbm_ct_gen3_manifest.json
public_data/burdenko_gbm_progression/manifests/burdenko_gbm_mr_gen3_manifest.json
public_data/burdenko_gbm_progression/manifests/burdenko_gbm_rtstruct_gen3_manifest.json
```

LUND-PROBE public code and directory documentation:

```text
public_data/lund_probe/LUND-PROBE-main/
scripts/prepare_lund_probe_multimodal_ctv_dataset.py
```

## Access Status

The CT+MR or MRI+sCT datasets are controlled-access datasets:

```text
GLIS-RT:
    NIH Controlled Data Access Policy / CRDC / dbGaP / Gen3

Burdenko-GBM-Progression:
    NIH Controlled Data Access Policy / CRDC / dbGaP / Gen3

LUND-PROBE:
    AIDA controlled access
```

The DRS metadata for GLIS-RT and Burdenko can be resolved anonymously, but raw object access returns authorization errors without approved credentials. This means the remaining blocker is not code, download URL discovery, or disk layout. It is controlled data authorization.

SegRap2025 LNCTVSeg is not blocked and is already available locally. Its limitation is modality scope: it provides ncCT/ceCT multimodal CT rather than CT+MR/PET.

## Use SegRap2025 LNCTVSeg

Data root:

```text
public_data/segrap2025_lnctv/extracted/LNCTVSeg-DataSet/
```

Recommended first public experiment:

```text
Internal_Cohort/imagesTr:
    volume_xxxx_0000.nii.gz = ncCT
    volume_xxxx_0001.nii.gz = ceCT

Internal_Cohort/labelsTr:
    volume_xxxx.nii.gz = LN CTV label map
```

Run the project sparse-prompt workflow by sampling K=3/5/7 slices from `labelsTr`, then evaluating completion/refinement against the full `labelsTr` label. Compare:

```text
ncCT-only
ceCT-only
ncCT+ceCT
```

Use the labeled testing cohorts for external center evaluation:

```text
Testing_Cohort_1: ceCT-only, 60 labeled cases
Testing_Cohort_2: ncCT-only, 32 labeled cases
Testing_Cohort_3: ceCT-only, 24 labeled cases
Testing_Cohort_4: ceCT-only, 24 labeled cases
```

## Gen3 Setup After Approval

The current server does not have the `gen3` command installed. After approval, install the Gen3 client in the environment selected for data acquisition, then configure credentials.

Expected credential variable:

```bash
export GEN3_CREDENTIALS_JSON=/path/to/credentials.json
```

Optional overrides:

```bash
export GEN3_PROFILE=nci-crdc
export GEN3_ENDPOINT=https://nci-crdc.datacommons.io
```

## Download GLIS-RT

Recommended first download:

```bash
bash scripts/download_gen3_drs_manifest.sh \
  public_data/glis_rt/manifests/glis_rt_all_gen3_manifest.json \
  public_data/glis_rt/raw_zips
```

If disk or time is limited, download only the required modalities:

```bash
bash scripts/download_gen3_drs_manifest.sh \
  public_data/glis_rt/manifests/glis_rt_ct_gen3_manifest.json \
  public_data/glis_rt/raw_zips_ct

bash scripts/download_gen3_drs_manifest.sh \
  public_data/glis_rt/manifests/glis_rt_mr_gen3_manifest.json \
  public_data/glis_rt/raw_zips_mr

bash scripts/download_gen3_drs_manifest.sh \
  public_data/glis_rt/manifests/glis_rt_rtstruct_gen3_manifest.json \
  public_data/glis_rt/raw_zips_rtstruct
```

## Download Burdenko-GBM-Progression

Full download:

```bash
bash scripts/download_gen3_drs_manifest.sh \
  public_data/burdenko_gbm_progression/manifests/burdenko_gbm_all_gen3_manifest.json \
  public_data/burdenko_gbm_progression/raw_zips
```

Minimal CTV completion subset:

```bash
bash scripts/download_gen3_drs_manifest.sh \
  public_data/burdenko_gbm_progression/manifests/burdenko_gbm_ct_gen3_manifest.json \
  public_data/burdenko_gbm_progression/raw_zips_ct

bash scripts/download_gen3_drs_manifest.sh \
  public_data/burdenko_gbm_progression/manifests/burdenko_gbm_mr_gen3_manifest.json \
  public_data/burdenko_gbm_progression/raw_zips_mr

bash scripts/download_gen3_drs_manifest.sh \
  public_data/burdenko_gbm_progression/manifests/burdenko_gbm_rtstruct_gen3_manifest.json \
  public_data/burdenko_gbm_progression/raw_zips_rtstruct
```

## Prepare LUND-PROBE After AIDA Download

After AIDA approval, place the extracted dataset under:

```text
public_data/lund_probe/raw/
```

Then run:

```bash
python scripts/prepare_lund_probe_multimodal_ctv_dataset.py \
  --raw-root public_data/lund_probe/raw \
  --out-root public_data/lund_probe/nnunet_like
```

Expected output:

```text
public_data/lund_probe/nnunet_like/imagesTr/
public_data/lund_probe/nnunet_like/labelsTr/
public_data/lund_probe/nnunet_like/dataset.json
```

## Validation Target

Once raw imaging is available, external validation should use the same project protocol:

```text
1. Convert full CTV masks from RTSTRUCT or provided NIfTI labels.
2. Simulate K=3/5/7 sparse CTV slice prompts.
3. Generate pseudo label with SDF propagation.
4. Build core-envelope.
5. Run anatomy-constrained refinement.
6. Report Dice, HD95, ASD, unseen-slice Dice, core precision, envelope recall, and delta Dice.
```

## Current Blocker

Raw multimodal CTV data cannot be downloaded until the PI or authorized institutional signatory obtains controlled-access approval. The server-side metadata, manifests, access templates, and download scripts are already prepared.
