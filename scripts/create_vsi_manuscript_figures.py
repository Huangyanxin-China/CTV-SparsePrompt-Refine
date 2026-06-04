#!/usr/bin/env python3
"""Create manuscript figures for the Pattern Recognition VSI package."""

import re
import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "manuscript_vsi_biomedical_data" / "figures"
TABLE_DIR = ROOT / "manuscript_vsi_biomedical_data" / "tables"
REPORT_FIGURE_DIR = ROOT / "reports" / "figures"
CLINICAL_OVERLAY_SCRIPTS = [
    "scripts/create_baseline_visualizations.py",
    "scripts/create_our_sdf_k7_visualization.py",
    "scripts/create_sammed3d_sparse_prompt_visualization.py",
]
CLINICAL_OVERLAY_STEMS = [
    "baseline_ctv_overlay",
    "baseline_oar_overlay",
    "sammed3d_sparse_prompt_k7_ctv_overlay",
    "our_sdf_k7_ctv_main_comparison",
]

COLORS = {
    "blue": "#0072B2",
    "sky": "#56B4E9",
    "green": "#009E73",
    "orange": "#E69F00",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
    "gray": "#6E6E6E",
}


def clean_tex_number(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    match = re.search(r"[-+]?\d*\.?\d+", text)
    return float(match.group(0)) if match else np.nan


def clean_tex_pair(value):
    if pd.isna(value):
        return np.nan, np.nan
    nums = re.findall(r"[-+]?\d*\.?\d+", str(value))
    if not nums:
        return np.nan, np.nan
    mean = float(nums[0])
    std = float(nums[1]) if len(nums) > 1 else np.nan
    return mean, std


def save(fig, stem):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=400, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def apply_style():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
        }
    )


def create_workflow():
    apply_style()
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    boxes = [
        (0.03, 0.56, 0.16, 0.23, "CT image\nOAR masks", COLORS["sky"]),
        (0.03, 0.18, 0.16, 0.23, "Sparse CTV\nslice prompts", COLORS["orange"]),
        (0.27, 0.37, 0.17, 0.25, "SDF\npropagation", COLORS["blue"]),
        (0.52, 0.37, 0.18, 0.25, "Core-envelope\nanalysis", COLORS["green"]),
        (0.78, 0.56, 0.18, 0.23, "Validated SDF\nCTV completion", COLORS["purple"]),
        (0.78, 0.18, 0.18, 0.23, "Doctor-prior\ngraph audit", COLORS["gray"]),
    ]
    for x, y, w, h, label, color in boxes:
        patch = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.015",
            facecolor=color,
            edgecolor="#222222",
            linewidth=1.0,
            alpha=0.95,
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", color="white", weight="bold")

    arrows = [
        ((0.19, 0.67), (0.27, 0.51)),
        ((0.19, 0.30), (0.27, 0.49)),
        ((0.44, 0.50), (0.52, 0.50)),
        ((0.70, 0.52), (0.78, 0.67)),
        ((0.70, 0.45), (0.78, 0.30)),
    ]
    for start, end in arrows:
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=14, linewidth=1.4, color="#333333"))

    ax.text(0.61, 0.25, r"$U = E - C$", ha="center", va="center", color="#222222", fontsize=11)
    ax.text(0.61, 0.17, "uncertain region", ha="center", va="center", color="#444444", fontsize=8)
    ax.set_title("Sparse-prompted CTV data preprocessing workflow", pad=8)
    save(fig, "vsi_method_workflow")
    shutil.copyfile(OUT_DIR / "vsi_method_workflow.png", OUT_DIR / "graphical_abstract.png")
    shutil.copyfile(OUT_DIR / "vsi_method_workflow.pdf", OUT_DIR / "graphical_abstract.pdf")


def create_main_results():
    apply_style()
    df = pd.read_csv(ROOT / "reports" / "ctv_main_experiment_results.csv")
    parsed = df["dice"].apply(clean_tex_pair)
    df["dice_value"] = df["dice_mean"].apply(clean_tex_number)
    df["dice_err"] = df["dice_std"].apply(clean_tex_number)
    df["dice_value"] = df["dice_value"].fillna(parsed.apply(lambda x: x[0]))
    df["dice_err"] = df["dice_err"].fillna(parsed.apply(lambda x: x[1]))
    order = [
        "nnU-Net 3d_fullres",
        "DiffUNet",
        "SAM-Med3D CT-derived",
        "SAM-Med3D sparse K=7",
        "Linear mask interpolation K=7",
        "SDF core K=7",
        "Support-intersection rule K=7",
        "SAM-Med3D full-GT prompt",
    ]
    df = df.set_index("method").loc[order].reset_index()
    labels = [
        "nnU-Net",
        "DiffUNet",
        "SAM-Med3D\nauto",
        "SAM-Med3D\nK=7",
        "Linear\nK=7",
        "SDF core\nK=7",
        "Support rule\nK=7",
        "SAM-Med3D\noracle",
    ]
    colors = [
        COLORS["gray"],
        COLORS["gray"],
        COLORS["orange"],
        COLORS["orange"],
        COLORS["blue"],
        COLORS["green"],
        COLORS["green"],
        COLORS["purple"],
    ]

    fig, ax = plt.subplots(figsize=(8.2, 3.3))
    x = np.arange(len(df))
    ax.bar(x, df["dice_value"], yerr=df["dice_err"], capsize=3, color=colors, edgecolor="#222222", linewidth=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    plt.setp(ax.get_xticklabels(), rotation=18, ha="right", rotation_mode="anchor")
    ax.set_ylabel("Dice")
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", alpha=0.25)
    ax.set_title("CTV test-set performance across automatic and sparse-prompt methods")
    ax.text(6, min(float(df.loc[6, "dice_value"]) + 0.08, 0.99), "0.928", ha="center", va="bottom", weight="bold")
    save(fig, "vsi_main_results_dice")


def create_doctor_prior_diagnostic():
    apply_style()
    df = pd.read_csv(ROOT / "results" / "doctor_prior_graph_refinement_fast10_k3_cached" / "doctor_prior_summary.csv")
    df = df[(df["split"] == "test") & (df["profile"] == "mild_expanded") & (df["k"] == 3)]
    order = ["sdf_base", "core_only", "learned_unary", "learned_graph_smooth", "oracle_upper_bound"]
    df = df.set_index("method").loc[order].reset_index()
    labels = ["SDF", "Core", "Learned\nunary", "Learned\ngraph", "Oracle"]
    colors = [COLORS["blue"], COLORS["green"], COLORS["orange"], COLORS["orange"], COLORS["purple"]]

    fig, ax = plt.subplots(figsize=(5.8, 3.0))
    x = np.arange(len(df))
    ax.bar(x, df["dice_mean"], yerr=df["dice_std"], capsize=3, color=colors, edgecolor="#222222", linewidth=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Dice")
    ax.set_ylim(0, 1.0)
    ax.grid(axis="y", alpha=0.25)
    ax.set_title("Doctor-prior diagnostic: learned prior does not close oracle gap")
    ax.annotate(
        "oracle headroom",
        xy=(4, float(df.loc[4, "dice_mean"])),
        xytext=(2.8, 0.90),
        arrowprops={"arrowstyle": "->", "lw": 1.0, "color": "#333333"},
        ha="center",
        va="bottom",
    )
    save(fig, "vsi_doctor_prior_diagnostic")


def create_prompt_sensitivity():
    apply_style()
    df = pd.read_csv(ROOT / "results" / "method_validation_ablation_suite" / "summary.csv")
    df = df[
        (df["profile"] == "mild_expanded")
        & (df["strategy"] == "even_nonempty")
        & (df["oar_mode"] == "pred_spinal")
        & (df["method"].isin(["sdf_base", "core_only", "oracle_upper_bound"]))
    ].copy()
    df = df.sort_values(["k", "method", "experiment"]).drop_duplicates(["k", "method"], keep="last")

    rows = []
    for k in [3, 5, 7]:
        by_method = df[df["k"] == k].set_index("method")
        sdf = by_method.loc["sdf_base"]
        core = by_method.loc["core_only"]
        oracle = by_method.loc["oracle_upper_bound"]
        rows.append(
            {
                "k": k,
                "sdf": sdf["dice_mean"],
                "sdf_std": sdf["dice_std"],
                "unseen": sdf["dice_unseen_slices_mean"],
                "unseen_std": sdf["dice_unseen_slices_std"],
                "core": core["dice_mean"],
                "oracle": oracle["dice_mean"],
                "oracle_gain": oracle["dice_mean"] - core["dice_mean"],
                "oracle_unseen_gain": oracle["dice_unseen_slices_mean"] - core["dice_unseen_slices_mean"],
            }
        )
    plot_df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.4, 3.1))
    x = np.arange(len(plot_df))
    ax.errorbar(
        x,
        plot_df["sdf"],
        yerr=plot_df["sdf_std"],
        color=COLORS["blue"],
        marker="o",
        linewidth=2.0,
        capsize=3,
        label="SDF completion",
    )
    ax.plot(x, plot_df["oracle"], color=COLORS["purple"], marker="s", linewidth=2.0, label="Oracle in envelope")
    ax.bar(
        x,
        plot_df["oracle"] - plot_df["core"],
        bottom=plot_df["core"],
        width=0.32,
        color=COLORS["purple"],
        alpha=0.18,
        edgecolor=COLORS["purple"],
        label="Recoverable headroom",
    )
    for idx, row in plot_df.iterrows():
        ax.text(idx, row["oracle"] + 0.018, f"+{row['oracle_gain']:.3f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"K={int(k)}" for k in plot_df["k"]])
    ax.set_ylabel("Dice")
    ax.set_xlabel("Number of sparse CTV prompt slices")
    ax.set_ylim(0.55, 1.02)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Prompt-count sensitivity and envelope oracle headroom")
    save(fig, "vsi_prompt_sensitivity_headroom")

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Prompt-count sensitivity for even-nonempty sparse CTV slice prompts on 31 scan-level test scans. The oracle rows quantify recoverable voxels inside the mild-expanded envelope and are not deployable.}",
        r"\label{tab:prompt-count-sensitivity}",
        r"\begin{tabular}{ccccc}",
        r"\toprule",
        r"$K$ & SDF Dice & SDF Unseen Dice & Oracle Dice & Oracle Gain \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            rf"{row['k']} & "
            rf"${row['sdf']:.3f} \pm {row['sdf_std']:.3f}$ & "
            rf"${row['unseen']:.3f} \pm {row['unseen_std']:.3f}$ & "
            rf"${row['oracle']:.3f}$ & "
            rf"${row['oracle_gain']:.3f}$ \\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    (TABLE_DIR / "prompt_count_sensitivity.tex").write_text("\n".join(lines))


def regenerate_clinical_overlays():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for script in CLINICAL_OVERLAY_SCRIPTS:
        subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT, check=True)
    for stem in CLINICAL_OVERLAY_STEMS:
        src = REPORT_FIGURE_DIR / f"{stem}.png"
        dst = OUT_DIR / f"{stem}.png"
        if not src.exists():
            raise FileNotFoundError(f"Expected regenerated clinical overlay is missing: {src}")
        shutil.copyfile(src, dst)


def main():
    create_workflow()
    create_main_results()
    create_prompt_sensitivity()
    create_doctor_prior_diagnostic()
    regenerate_clinical_overlays()
    print(f"Wrote figures to {OUT_DIR}")


if __name__ == "__main__":
    main()
