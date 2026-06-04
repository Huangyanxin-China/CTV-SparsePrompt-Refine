# GTV/CTV Target Visualization Reproduction Package

This package contains the CT images and target masks needed to reproduce the CTV/GTV difference visualization for the 32 cases that have both CTV and GTV labels.

## Contents

- `visualize_gtv_ctv_targets.py`: main reproduction script.
- `nnUNet_raw_GTV_CTV_Organ/Dataset502_ChestCTV`: CT images and CTV labels for the overlapping cases.
- `nnUNet_raw_GTV_CTV_Organ/Dataset503_ChestGTV`: CT images and GTV labels for the overlapping cases.
- `outputs/gtv_ctv_target_visualization`: generated PNGs, CSV statistics, and summary from the original run.
- `code`: helper scripts used for DICOM/RTSTRUCT scanning, broad ROI-name matching, and nnUNet export.
- `resources`: audit CSV/JSON resources and the earlier organ/ROI audit PPT report.

Original clinical DICOM folders are not included. If you need to rebuild the nnUNet data from DICOM, place the exported clinical folders under this package root and use the scripts in `code` or the matching top-level scripts from the original workspace.

## Reproduce on a Linux server

```bash
cd gtv_ctv_repro_package_20260604
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python visualize_gtv_ctv_targets.py
```

The regenerated outputs will be written to:

```text
outputs/gtv_ctv_target_visualization/
```

Key files after running:

- `outputs/gtv_ctv_target_visualization/gtv_ctv_both_cases_stats.csv`
- `outputs/gtv_ctv_target_visualization/selected_gtv_ctv_difference_contact_sheet.png`
- `outputs/gtv_ctv_target_visualization/all_gtv_ctv_difference_contact_sheet.png`
- `outputs/gtv_ctv_target_visualization/case_pngs/*_gtv_ctv_difference.png`

## Color legend

- Blue: CTV-only region.
- Yellow: CTV and GTV overlap.
- Red: GTV outside CTV.

## Notes

Large red regions may indicate inconsistent target hierarchy, different lesions, multiple exported RTSTRUCTs, or true contour disagreement. These cases should be reviewed manually before using the masks as ground truth.
