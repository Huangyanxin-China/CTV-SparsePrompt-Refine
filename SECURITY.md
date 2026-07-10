# Security Policy

## Supported versions

Security fixes are applied to the current `main` branch.

## Reporting a vulnerability

Please do not open a public issue for vulnerabilities that could expose clinical data, credentials, private paths, or restricted artifacts. Use the repository's private GitHub security advisory flow:

```text
https://github.com/Huangyanxin-China/CTV-SparsePrompt-Refine/security/advisories/new
```

Include the affected file or commit, reproduction steps, potential impact, and any suggested mitigation. Do not attach patient data or institutional credentials.

## Clinical-data boundary

This repository is research software and is not a medical device. Public contributions must not contain identifiable or reversible medical data. Removing DICOM headers alone is not sufficient evidence of de-identification; rendered clinical images require the appropriate institutional review and release approval.
