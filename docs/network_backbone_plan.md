# Network Backbone Plan

This project keeps network experiments separate from the non-network pseudo
label pipeline. The goal is controlled comparison, not replacing the current
structure-preserving propagation by default.

## Available Backbones

### `unet3d`

Role: ordinary supervised segmentation baseline.

Input:

```text
CT or multi-channel prior tensor -> binary CTV logits
```

Use this to answer whether a small 3D CNN trained on pseudo labels can improve
over direct pseudo-label inference. If it underperforms direct pseudo labels,
it should remain only a baseline.

### `sdf_refine_unet`

Role: SDF residual refinement baseline.

Input:

```text
CT, propagated SDF, propagated mask, uncertainty, organ priors
```

Output:

```text
Delta Phi
```

Fusion rule:

```text
Phi_final = Phi_prop + DeltaPhi
Y_final = 1[Phi_final > 0]
```

This model has the same lightweight residual U-Net backbone as `unet3d`, but
the learning target is boundary displacement rather than direct semantic mask
prediction.

### `sam_med3d`

Role: prompt-based foundation-model comparison and optional slice/volume
refinement branch.

Source:

```text
/share3/home/huangyanxin/SAM-Med3D-main
```

Default checkpoint:

```text
/share3/home/huangyanxin/SAM-Med3D-main/ckpt/sam_med3d_turbo.pth
```

The current project uses a thin adapter instead of copying the full external
repository. The adapter supports:

```text
CT volume
box prompt: x0,y0,z0,x1,y1,z1
point prompt: x,y,z with foreground/background labels
optional mask input
```

The local checkpoint matches the `vit_b_ori` SAM-Med3D variant with 128 cubic
input size, so `vit_b_ori` is the default model type in this project.

## Recommended Comparisons

Use the same 1mm ROI and same sparse prompts for all methods:

```text
A. Direct non-network pseudo label
B. UNet3D trained on pseudo label
C. SDFRefineNet using non-network pseudo label as Phi_prop
D. SAM-Med3D prompt inference / fine-tuning
E. Non-network pseudo label + SAM/UNet residual fusion
```

The network branch is useful only if it improves over A. Otherwise the direct
non-network pseudo label remains the primary result.

## Sanity Checks

Check local CNN backbones:

```bash
python scripts/check_network_backbones.py
```

Check SAM-Med3D construction and tensor shapes:

```bash
python scripts/check_network_backbones.py --models sam_med3d --sam_shape 64 64 64
```

The SAM check loads the external checkpoint and may use substantial memory.
