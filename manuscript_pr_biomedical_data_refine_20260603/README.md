# Pattern Recognition Initial Draft Package

Draft date: 2026-06-03

This package rewrites the manuscript around the latest result:

- Input support-intersection pseudo-label Dice: 0.9278
- Supervised pseudo-to-true refine network Dice: 0.9341
- Mean paired Delta Dice: +0.0063
- One-sided paired t-test: p = 3.46e-05
- One-sided Wilcoxon: p = 4.33e-05
- Test set: 31 CTV-positive scan-level cases

## Target venue framing

Target journal: Pattern Recognition.

Target special issue: `VSI: PR_Biomedical Data`, "Multimodal Pattern Recognition for Biomedical Data: Theories, Algorithms and Applications".

The manuscript is framed under `medical data processing`, not strict CT/MRI/PET multimodal imaging. The data use planning CT as the imaging modality, while OAR masks, sparse prompts, SDF maps, pseudo-labels, and distance channels are described as preprocessing/context channels.

The ScienceDirect special-issue page lists `medical data processing` as a keyword and the submission article type as `VSI: PR_Biomedical Data`. It also lists the submission window as 01-Feb-2026 to 31-Aug-2026.

## Official writing and formatting points used

Checked from ScienceDirect on 2026-06-03:

- Pattern Recognition guide requests single-column, double-spaced manuscript source with numbered pages.
- Abstract should be concise and standalone.
- Keywords should be limited to 1--7.
- Highlights should contain 3--5 bullet points, with each bullet no longer than 85 characters.
- The title avoids unexplained abbreviations; the abstract expands CTV, OAR, SDF, HD95, and ASD at first use.
- Figures and tables should be embedded near the relevant text in the manuscript.
- References should use numbered square-bracket style.
- The special issue article type is `VSI: PR_Biomedical Data`.

## Files

- `main.tex`: new full English initial manuscript draft.
- `highlights.tex`: Elsevier-style highlights.
- `references.bib`: bibliography copied from the previous manuscript assets.
- `tables/`: newly written tables centered on the latest refine-network result.
- `figures/workflow_with_network.png`: one-page workflow figure with network inset.
- `figures/refine_network_architecture.png`: network structure inset.
- `figures/method_visual_comparison_example.png`: qualitative method comparison from raw NIfTI outputs.
- `figures/ablation_visual_progression_example.png`: qualitative ablation progression from raw NIfTI outputs.
- `figures/sdf_completion_qualitative.png`: qualitative SDF completion figure from earlier report assets.

## Table organization

The tables were reorganized to match the common style used in the reference medical segmentation papers:

- three-line `booktabs` tables without vertical rules;
- compact captions, with implementation details moved to table notes;
- grouped method families in the main comparison table;
- validation/test/statistical evidence separated in the refine analysis table;
- progressive component ablation with check-mark columns to show the methodological buildup;
- multi-column headers for auxiliary OAR model comparison.

## Compilation

The current server does not expose a TeX engine (`pdflatex`, `xelatex`, `latexmk`, or `kpsewhich` were not available), so local PDF compilation was not performed here.

On Overleaf or a machine with TeX Live:

```bash
xelatex main
bibtex main
xelatex main
xelatex main
```

If using Overleaf, set the compiler to XeLaTeX.

## Items requiring author completion before submission

- Replace placeholder author affiliation and email.
- Confirm IRB / ethics statement and data-use permissions.
- Complete the CRediT author contribution statement for the final author list.
- Confirm funding statement.
- Review the generative AI declaration and adapt to institutional policy.
- Verify all references in `references.bib`; Pattern Recognition recommends accurate numbered references and generally expects 35--55 relevant references.
- Add a cover letter and declaration of competing interests form during final submission.
