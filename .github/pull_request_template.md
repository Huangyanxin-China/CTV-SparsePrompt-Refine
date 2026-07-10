## Summary

<!-- What changed and why? -->

## Scientific and user impact

<!-- Does this change inputs, outputs, evaluation, or reported behavior? -->

## Validation

- [ ] `python -m compileall -q models scripts utils tests`
- [ ] `ruff check models scripts utils tests`
- [ ] `pytest -q`
- [ ] Documentation updated where needed
- [ ] No private clinical data, identifiers, paths, checkpoints, or generated predictions added

## Data and evaluation integrity

- [ ] No held-out test labels were used to select a method, threshold, or checkpoint
- [ ] Oracle/diagnostic results are clearly labeled
- [ ] Missing and empty predictions are reported
- [ ] Medical-image geometry is validated
