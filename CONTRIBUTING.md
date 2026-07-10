# Contributing

Thank you for improving CTV Sparse-Prompt Refinement.

## Before opening a change

- Open an issue for behavior changes, new methods, or changes to evaluation protocol.
- Never upload clinical volumes, DICOM files, NIfTI files, checkpoints trained on restricted data, case identifiers, private paths, or institutional metadata.
- Keep scientific claims separate from diagnostic or oracle-only analyses.
- Do not tune a released configuration on the held-out test set.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
```

Run the local checks:

```bash
python -m compileall -q models scripts utils tests
ruff check models scripts utils tests
pytest -q
```

## Pull requests

1. Create a focused branch.
2. Add or update tests for behavior changes.
3. Update the README or documentation when commands, inputs, or outputs change.
4. Describe the data split and whether any complete labels were used for prompt simulation, calibration, validation, or testing.
5. Confirm that the privacy checks in `docs/privacy_release_checklist.md` pass.

Pull requests should not contain generated predictions, private result tables, local environment files, or manuscript submission materials.

## Reporting scientific results

Report the exact commit, configuration, dependency environment, random seed, split manifest, missing-prediction count, and empty-prediction count. Oracle results must be labeled as diagnostic upper bounds and must not be used to select the final test configuration.
