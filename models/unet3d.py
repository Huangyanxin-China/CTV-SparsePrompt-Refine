import torch
import torch.nn as nn
import torch.nn.functional as F


def _group_count(channels, groups=8):
    groups = min(int(groups), int(channels))
    while groups > 1 and channels % groups != 0:
        groups -= 1
    return groups


class ResBlock3D(nn.Module):
    def __init__(self, in_channels, out_channels, groups=8):
        super().__init__()
        g = _group_count(out_channels, groups)
        self.conv1 = nn.Conv3d(in_channels, out_channels, 3, padding=1, bias=False)
        self.norm1 = nn.GroupNorm(g, out_channels)
        self.conv2 = nn.Conv3d(out_channels, out_channels, 3, padding=1, bias=False)
        self.norm2 = nn.GroupNorm(g, out_channels)
        if in_channels == out_channels:
            self.shortcut = nn.Identity()
        else:
            self.shortcut = nn.Sequential(
                nn.Conv3d(in_channels, out_channels, 1, bias=False),
                nn.GroupNorm(g, out_channels),
            )

    def forward(self, x):
        residual = self.shortcut(x)
        x = F.relu(self.norm1(self.conv1(x)), inplace=True)
        x = self.norm2(self.conv2(x))
        return F.relu(x + residual, inplace=True)


class UNet3D(nn.Module):
    """Small residual 3D U-Net for binary CTV segmentation baselines."""

    def __init__(self, in_channels=1, out_channels=1, base_filters=16):
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
        return F.interpolate(x, size=ref.shape[-3:], mode="trilinear", align_corners=False)

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
