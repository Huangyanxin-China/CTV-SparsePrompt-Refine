import torch
import torch.nn as nn

from .unet3d import ResBlock3D


class SDFRefineNet(nn.Module):
    """Small residual 3D U-Net for constrained CTV pseudo-label refinement.

    The network is intentionally generic: callers may train the single output
    channel as an SDF residual, an inclusion logit, or another scalar correction
    field. The final clinical constraint, for example forcing predictions to
    stay inside an SDF envelope, belongs in the training/inference script.
    """

    def __init__(self, in_channels=9, out_channels=1, base_filters=12):
        super().__init__()
        f = int(base_filters)
        self.en1 = ResBlock3D(in_channels, f)
        self.pool1 = nn.MaxPool3d(2)
        self.en2 = ResBlock3D(f, f * 2)
        self.pool2 = nn.MaxPool3d(2)
        self.en3 = ResBlock3D(f * 2, f * 4)
        self.pool3 = nn.MaxPool3d(2)
        self.bridge = ResBlock3D(f * 4, f * 8)

        self.up3 = nn.ConvTranspose3d(f * 8, f * 4, 2, stride=2)
        self.de3 = ResBlock3D(f * 8, f * 4)
        self.up2 = nn.ConvTranspose3d(f * 4, f * 2, 2, stride=2)
        self.de2 = ResBlock3D(f * 4, f * 2)
        self.up1 = nn.ConvTranspose3d(f * 2, f, 2, stride=2)
        self.de1 = ResBlock3D(f * 2, f)
        self.out = nn.Conv3d(f, out_channels, 1)

    @staticmethod
    def _match_size(x, ref):
        if x.shape[-3:] == ref.shape[-3:]:
            return x
        return nn.functional.interpolate(x, size=ref.shape[-3:], mode="trilinear", align_corners=False)

    def forward(self, x):
        x1 = self.en1(x)
        x2 = self.en2(self.pool1(x1))
        x3 = self.en3(self.pool2(x2))
        bridge = self.bridge(self.pool3(x3))

        u3 = self._match_size(self.up3(bridge), x3)
        d3 = self.de3(torch.cat([u3, x3], dim=1))
        u2 = self._match_size(self.up2(d3), x2)
        d2 = self.de2(torch.cat([u2, x2], dim=1))
        u1 = self._match_size(self.up1(d2), x1)
        d1 = self.de1(torch.cat([u1, x1], dim=1))
        return self.out(d1)
