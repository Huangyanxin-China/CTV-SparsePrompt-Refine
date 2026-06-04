# LUND-PROBE AIDA Access Request Template

Dataset:

```text
LUND-PROBE - LUND Prostate Radiotherapy Open Benchmarking and Evaluation dataset
DOI: 10.23698/aida/lund-probe
Dataset page: https://datahub.aida.scilifelab.se/10.23698/aida/lund-probe
```

## Project Title

```text
Sparse-prompted multimodal radiotherapy target completion using MRI, synthetic CT, OAR constraints, and SDF core-envelope priors
```

## Short Project Description

```text
We are developing a sparse-prompted radiotherapy target completion method. The method uses a small number of 2D target annotations as sparse prompts and converts them into a 3D target candidate through signed distance function propagation. It then constructs a high-precision core and high-recall envelope, incorporates organ-at-risk anatomical constraints, and performs constrained refinement within the uncertain region.

Our institutional thoracic CTV dataset is private and cannot be publicly released. We request access to LUND-PROBE to evaluate the reproducibility and multimodal extension of the method on a public radiotherapy dataset containing MRI, synthetic CT, CTV/PTV labels, and OAR segmentations.
```

## Why LUND-PROBE Is Needed

```text
LUND-PROBE is uniquely suitable because it contains radiotherapy target delineations, including CTV and PTV, as well as MRI and synthetic CT images. This enables us to test whether multimodal information improves sparse-prompt CTV completion compared with MRI-only input. The dataset also provides OAR masks and observer-related structures, which are directly aligned with our method's anatomy-constrained target refinement design.
```

## Planned Data Use

```text
1. Use MRI T2 and synthetic CT volumes as multimodal inputs.
2. Use clinical CTV masks to simulate sparse 2D target prompts.
3. Use OAR masks to define anatomical constraints.
4. Evaluate sparse-prompt SDF propagation and core-envelope refinement.
5. Compare MRI-only and MRI+sCT variants.
6. Report aggregate metrics only; no attempt will be made to re-identify subjects.
```

## Planned Outputs

```text
The study will report only aggregate segmentation metrics, such as Dice, HD95, ASD, unseen-slice Dice, core precision, and envelope recall. No subject-level identifiable information or raw imaging data will be redistributed.
```

## Data Security Plan

```text
The data will be stored on an access-controlled institutional server. Only authorized project members will access the dataset. Raw imaging files will not be uploaded to public repositories or shared outside the approved research environment. Derived code and aggregate results may be shared publicly, but raw data will remain under the original access terms.
```

## Suggested Manuscript Usage

```text
The private thoracic CTV dataset will be used as the primary clinical validation cohort. LUND-PROBE will be used as an external public multimodal radiotherapy validation cohort to test the reproducibility and generalization of the sparse-prompt target completion strategy.
```

## Contact / Signatory Reminder

The AIDA page states that the recipient researcher must hold at least a PhD degree in a relevant field and that the applicant should be an authorized signatory able to enter data sharing agreements on behalf of the institution. This application should therefore be submitted by the PI or an institutionally authorized researcher.
