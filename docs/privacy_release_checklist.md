# Public Release Privacy Checklist

Use this checklist before pushing to a public GitHub repository.

## Required Scope

- Keep method code, generic documentation, environment requirements, and
  de-identified 2D CT/contour result renderings.
- Exclude reversible medical volumes, full raw clinical image exports, label
  volumes, DICOM, NIfTI, model checkpoints, generated prediction volumes, local
  logs, and manuscript files that describe private data.
- If real-result visualizations are included, they must be rendered PNG/GIF/HTML
  views of de-identified 2D CT crops and contour overlays only, with no case
  names, acquisition dates, private paths, or clinical metadata.
- Avoid dataset-specific sample counts, split details, case identifiers,
  acquisition dates, institution names, server paths, or private study labels.

## Automated Checks

Run from the repository root:

```bash
git status --short --branch
```

Confirm no medical volumes, checkpoints, archives, documents, or PDFs are
tracked or staged:

```bash
find . -type f \( \
  -name '*.nii' -o -name '*.nii.gz' -o -name '*.dcm' -o \
  -name '*.pt' -o -name '*.pth' -o -name '*.ckpt' -o \
  -name '*.npz' -o -name '*.pkl' -o -name '*.model' -o \
  -name '*.zip' -o -name '*.tar.gz' -o \
  -name '*.docx' -o -name '*.pdf' \
\) -print
```

Search for private paths, internal dataset names, case/date-like identifiers,
and private-data language:

```bash
rg -n "/share3|Dataset0|server0|server-0|private cohort|institutional|patient_[A-Za-z0-9]|CT20[0-9]{6}|P[0-9]{6,}|hospital|医院|患者|病例|数据集"
```

Check large tracked files:

```bash
git ls-files -z | xargs -0 du -h | sort -hr | head -30
```

Check ignored local artifacts before staging:

```bash
git status --ignored --short
```

## Manual Review

- Open `README.md` and confirm examples use placeholders such as
  `/path/to/local_dataset`.
- Open `site/index.html` and confirm visualizations are de-identified 2D CT
  crops and contour overlays, with no case IDs, dates, private paths, or
  private result values.
- Confirm `site/assets/real_ct_single_case_slices.gif`,
  `site/assets/real_ct_multi_method_comparison.png`,
  `site/assets/real_ct_workflow_demo.gif`, and `site/real-results/` contain only
  generic sequential slice labels and de-identified rendered display images.
- Confirm `.gitignore` covers local data, checkpoints, outputs, logs, archives,
  manuscript exports, and office documents.

## Push Permission Check

Before a real push, run:

```bash
git remote -v
git ls-remote --heads origin
git push --dry-run origin HEAD:main
```

The dry run should authenticate successfully. If it fails, configure one of:

- HTTPS remote plus a GitHub personal access token with repository write
  permission.
- SSH remote plus an SSH key added to the target GitHub account.
- Collaborator or organization permission to push to the target repository.
