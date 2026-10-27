# `Data/` — put the three raw `.mat` files here

Nothing in this directory is committed (`Data/` is in `.gitignore`); the raw files are
multi-gigabyte and are distributed by Toyota Research Institute, not by this repository.

Download them from the dataset page:

**<https://data.matr.io/1/projects/5c48dd2bc625d700019f3204>**
(TRI Energy & Materials Data, *Data-driven prediction of battery cycle life before
capacity degradation*, 23 January 2019, licensed **CC BY 4.0**)

Place exactly these three files directly in this directory:

| file | bytes | SHA-256 |
|---|---|---|
| `2017-05-12_batchdata_updated_struct_errorcorrect.mat` | 3,025,320,241 | `9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba` |
| `2017-06-30_batchdata_updated_struct_errorcorrect.mat` | 2,007,331,155 | `63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8` |
| `2018-04-12_batchdata_updated_struct_errorcorrect.mat` | 3,236,690,412 | `62c30e413b63e6144720e016deed3661fac8468641794a5807b123fe84717998` |

Verify from the repository root:

```bash
sha256sum -c <<'SUMS'
9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba  Data/2017-05-12_batchdata_updated_struct_errorcorrect.mat
63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8  Data/2017-06-30_batchdata_updated_struct_errorcorrect.mat
62c30e413b63e6144720e016deed3661fac8468641794a5807b123fe84717998  Data/2018-04-12_batchdata_updated_struct_errorcorrect.mat
SUMS
```

The dataset page also offers a 2019-01-24 batch and two further 2018 batches. Nothing in
`exploration/` reads them, and they are outside the 124-cell published dataset.

Every file here is opened `mode="r"` throughout. No code in this repository writes to
`Data/`.
