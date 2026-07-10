# Reproducibility Guide

This repository intentionally excludes clinical volumes, labels, predictions, and checkpoints. Reproduction therefore requires a local dataset that follows the documented geometry and naming contract.

## Freeze the protocol before testing

Before evaluating the held-out test set, record:

- repository commit SHA;
- Python and dependency versions;
- case-to-subject mapping and split manifest;
- prompt count and prompt-selection strategy;
- SDF/core-envelope profile;
- preprocessing rule and its calibration split;
- model checkpoint and probability threshold;
- label mapping and image geometry policy;
- random seeds.

Configuration screening and threshold selection belong to training or validation data. Complete test labels may be used to simulate retrospective sparse prompts and compute final metrics, but not to choose the reported method.

## Recommended run record

```bash
git rev-parse HEAD
python --version
python -m pip freeze > environment.freeze.txt
```

Keep a machine-readable run manifest next to results. At minimum it should contain the command, commit, input manifest hash, configuration, seed, selected checkpoint, selected threshold, and output paths.

## Evaluation requirements

- Enumerate the ground-truth manifest, not only files that happen to exist in the prediction directory.
- Treat missing predictions as failures unless an explicitly documented debug flag is used.
- Report empty-prediction and invalid-surface-metric counts.
- Check shape, spacing, origin, and direction before comparing medical volumes.
- Report patient-level statistics when multiple scans can belong to one patient.
- Label oracle upper bounds separately and never use them to tune the final test configuration.

## Minimal verification

```bash
python -m compileall -q models scripts utils tests
ruff check models scripts utils tests
pytest -q
```

All tests use synthetic arrays and do not require private data.
