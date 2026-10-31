# Dataset: LEVIR-CD

* **What**: 637 pairs of 1024×1024 Google-Earth images (0.5 m/px, 2002–2018, Texas, USA) with building-change masks.
  Official split: train 445 / val 64 / test 128 pairs (verified locally: `GET /api/model/dataset`).
* **Official source**: <https://levir.buaa.edu.cn/datasets/> (LEVIR-CD). Paper: H. Chen & Z. Shi, *A Spatial-Temporal
  Attention-Based Method and a New Dataset for Remote Sensing Image Change Detection*, Remote Sensing 12(10):1662, 2020.
* **Terms**: for research/academic use; imagery originates from Google Earth. **TerraTrace does not redistribute the dataset**
  and `data/raw/` is git-ignored. Please read the authors' terms before use.
* **How the development copy was obtained**: the official page links to Baidu/Google Drive downloads that require
  interactive access. The numbers reported in this repository were produced from the Hugging Face mirror
  `satellite-image-deep-learning/LEVIR-CD` (`train.zip`, `val.zip`, `test.zip`, original 1024×1024 files; 445/64/128 pairs,
  matching the official counts). This is a **third-party mirror**; its provenance was not independently verified beyond
  the matching split sizes and the readable image/mask pairs.

## Layout expected by the loader

```
data/raw/LEVIR-CD/{train,val,test}/{A,B,label}/<name>.png     # A = earlier, B = later, label ∈ {0,255}
```

```bash
mkdir -p data/raw/LEVIR-CD/{train,val,test}
for s in train val test; do
  curl -L -o /tmp/$s.zip https://huggingface.co/datasets/satellite-image-deep-learning/LEVIR-CD/resolve/main/$s.zip
  python -c "import zipfile; zipfile.ZipFile('/tmp/$s.zip').extractall('data/raw/LEVIR-CD/$s')"
done
```

## Statistics (sampled from the local copy)

| Split | Pairs | Changed-pixel fraction |
|---|---|---|
| train | 445 | ≈ 5.6 % |
| val | 64 | ≈ 4.2 % |
| test | 128 | ≈ 5.1 % |

Strong class imbalance (≈ 95 % no-change) is why training uses BCE + Dice and why F1/IoU (not accuracy) are reported.

## Demo imagery (separate from LEVIR-CD)

`data/samples/naip_leander/` holds three 640 m × 640 m windows of **USDA NAIP** aerial imagery (public domain) over Leander,
Texas — 2018-11-03, 2020-06-08 and 2022 acquisitions — fetched by `scripts/fetch_naip_demo.py` through the Microsoft Planetary
Computer STAC API. See `SOURCE.json` there for item IDs.
