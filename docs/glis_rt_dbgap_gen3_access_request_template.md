# GLIS-RT dbGaP / CRDC Access Request Template

Dataset:

```text
GLIS-RT - Glioma Image Segmentation for Radiotherapy: RT targets, barriers to cancer spread, and organs at risk
TCIA DOI: https://doi.org/10.7937/TCIA.T905-ZQ20
TCIA page: https://www.cancerimagingarchive.net/collection/glis-rt/
dbGaP / accession in manifest: phs004225
```

## Project Title

```text
Sparse-prompted multimodal radiotherapy CTV completion using CT, MRI, OAR constraints, and SDF core-envelope priors
```

## Short Research Use Statement

```text
We request access to the GLIS-RT dataset to evaluate a sparse-prompted radiotherapy target completion method on a public multimodal CTV dataset. Our method uses a small number of 2D clinical target annotations as sparse prompts and propagates them into a 3D candidate target through signed distance function propagation. It then constructs a high-precision core and high-recall envelope, incorporates anatomical constraints, and refines the uncertain target region.

Our primary institutional thoracic CTV dataset is private and cannot be publicly released. GLIS-RT provides CT, MR, image registration, and RTSTRUCT data with GTV/CTV/OAR annotations, enabling public multimodal validation of the proposed target completion pipeline.
```

## Planned Data Use

```text
1. Download CT, MR, REG, and RTSTRUCT DICOM series for GLIS-RT cases.
2. Convert CT/MR images and RTSTRUCT target/OAR contours to NIfTI.
3. Use CTV contours to simulate sparse 2D target prompts.
4. Run sparse prompt -> SDF propagation -> core-envelope construction.
5. Evaluate MRI/CT multimodal target completion against full CTV annotations.
6. Report aggregate segmentation metrics only.
```

## Security and Sharing

```text
The data will be stored on an access-controlled institutional server. Raw GLIS-RT files will not be redistributed or uploaded to public repositories. Published results will contain only aggregate metrics and non-identifying visual examples permitted by the data-use policy. Code, preprocessing scripts, and derived aggregate tables may be shared separately.
```

## Local Files Already Prepared

The public manifest and Gen3 manifest files are already prepared in this project:

```text
public_data/glis_rt/GC_manifest_GLIS-RT_20260326.csv
public_data/glis_rt/GLIS-RT-manifest-nbia-digest.xlsx
public_data/glis_rt/manifests/glis_rt_all_gen3_manifest.json
public_data/glis_rt/manifests/glis_rt_ct_gen3_manifest.json
public_data/glis_rt/manifests/glis_rt_mr_gen3_manifest.json
public_data/glis_rt/manifests/glis_rt_rtstruct_gen3_manifest.json
public_data/glis_rt/manifests/glis_rt_reg_gen3_manifest.json
```

After access is approved and a CRDC/Gen3 credential JSON is available, set:

```bash
export GEN3_CREDENTIALS_JSON=/path/to/credentials.json
```

Then run:

```bash
bash scripts/download_gen3_drs_manifest.sh \
  public_data/glis_rt/manifests/glis_rt_all_gen3_manifest.json \
  public_data/glis_rt/raw_zips
```
