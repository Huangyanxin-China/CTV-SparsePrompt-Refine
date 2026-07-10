# Data, Model, and Asset Policy

## Repository scope

The repository contains source code, generic documentation, and rendered demonstration assets. It does not distribute raw clinical volumes, segmentation label volumes, DICOM objects, private split manifests, generated predictions, or trained checkpoints.

Users must obtain and govern their own datasets and third-party weights under the applicable institutional approvals, data-use agreements, and licenses.

## Prohibited contributions

Do not commit or attach:

- protected health information or patient identifiers;
- DICOM or NIfTI clinical volumes;
- reversible exports of restricted data;
- private case names, acquisition dates, server paths, or credentials;
- checkpoints or embeddings derived from restricted data without explicit release approval;
- third-party source, weights, or assets whose license does not permit redistribution.

## Demonstration assets

Rendered PNG, GIF, and HTML assets are not automatically covered by a future source-code license. Their continued publication requires confirmation that the appropriate rights, privacy review, and institutional release approval exist. File-name anonymization and metadata removal alone do not establish that an image is safe to publish.

## External models and datasets

External adapters do not redistribute third-party source trees or checkpoints. Users are responsible for installing external software and obtaining model weights under their original terms.

## Incident response

If restricted data or identifying information is found in the repository, do not repost it in a public issue. Use the private reporting path described in `SECURITY.md`.
