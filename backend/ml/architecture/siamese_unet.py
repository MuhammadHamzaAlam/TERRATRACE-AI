"""Siamese U-Net change-detection network with a shared-weight ResNet18 encoder.

Both temporal images pass through the *same* encoder (shared weights). At each of the five
scales the two feature maps are compared by concatenating [f_t1, f_t2, |f_t1 - f_t2|] and fusing with a
1x1 conv. A U-Net decoder with skip connections from the fused features produces a per-pixel change logit.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision


def _conv_block(cin: int, cout: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
    )


class SharedResNet18Encoder(nn.Module):
    CHANNELS = (64, 64, 128, 256, 512)  # strides 2,4,8,16,32

    def __init__(self, pretrained: bool = False):
        super().__init__()
        weights = None
        if pretrained:
            try:
                weights = torchvision.models.ResNet18_Weights.IMAGENET1K_V1
            except Exception:  # pragma: no cover
                weights = None
        try:
            net = torchvision.models.resnet18(weights=weights)
        except Exception as e:  # network failure while fetching weights -> fall back, caller is told
            print(f"[warn] could not load pretrained ResNet18 weights ({e}); using random init")
            net = torchvision.models.resnet18(weights=None)
        self.stem = nn.Sequential(net.conv1, net.bn1, net.relu)
        self.pool = net.maxpool
        self.layer1, self.layer2, self.layer3, self.layer4 = net.layer1, net.layer2, net.layer3, net.layer4

    def forward(self, x: torch.Tensor) -> list[torch.Tensor]:
        f0 = self.stem(x)
        f1 = self.layer1(self.pool(f0))
        f2 = self.layer2(f1)
        f3 = self.layer3(f2)
        f4 = self.layer4(f3)
        return [f0, f1, f2, f3, f4]


class SiameseUNet(nn.Module):
    def __init__(self, pretrained: bool = False, decoder_channels=(256, 128, 64, 32)):
        super().__init__()
        self.encoder = SharedResNet18Encoder(pretrained)
        ch = SharedResNet18Encoder.CHANNELS
        self.fuse = nn.ModuleList([
            nn.Sequential(nn.Conv2d(c * 3, c, 1, bias=False), nn.BatchNorm2d(c), nn.ReLU(inplace=True)) for c in ch
        ])
        d = decoder_channels
        self.dec4 = _conv_block(ch[4] + ch[3], d[0])
        self.dec3 = _conv_block(d[0] + ch[2], d[1])
        self.dec2 = _conv_block(d[1] + ch[1], d[2])
        self.dec1 = _conv_block(d[2] + ch[0], d[3])
        self.head = nn.Sequential(_conv_block(d[3], 16), nn.Conv2d(16, 1, 1))

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        """Returns change *logits* of shape (B,1,H,W). Apply sigmoid for probabilities."""
        h, w = x1.shape[-2:]
        f1, f2 = self.encoder(x1), self.encoder(x2)  # shared weights
        fused = [m(torch.cat([a, b, (a - b).abs()], dim=1)) for m, a, b in zip(self.fuse, f1, f2)]
        x = fused[4]
        x = self.dec4(torch.cat([F.interpolate(x, size=fused[3].shape[-2:], mode="bilinear", align_corners=False), fused[3]], 1))
        x = self.dec3(torch.cat([F.interpolate(x, size=fused[2].shape[-2:], mode="bilinear", align_corners=False), fused[2]], 1))
        x = self.dec2(torch.cat([F.interpolate(x, size=fused[1].shape[-2:], mode="bilinear", align_corners=False), fused[1]], 1))
        x = self.dec1(torch.cat([F.interpolate(x, size=fused[0].shape[-2:], mode="bilinear", align_corners=False), fused[0]], 1))
        x = F.interpolate(x, size=(h, w), mode="bilinear", align_corners=False)
        return self.head(x)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
