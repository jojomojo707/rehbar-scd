# D1B5 embedding module evaluation

Run timestamp (UTC): `2026-11-21T19:12:48.190654+00:00`
Seed: `20261122`
Model: `BAAI/bge-small-en-v1.5` (384 dimensions), FastEmbed `0.9.1`, ONNX Runtime `1.31.1`
Device: `CPUExecutionProvider`; ONNX file SHA-256: `model_optimized.onnx=51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431`
Hardware: `Intel64 Family 6 Model 186 Stepping 3, GenuineIntel`, 12 logical CPUs, `Windows-11-10.0.26200-SP0`, Python `3.12.16`, 1 thread(s).

## Semantic module results

| Pair type | Count | Mean cosine |
| --- | ---: | ---: |
| Paraphrase | 15 | 0.857224 |
| Unrelated | 15 | 0.555263 |
| Gap (paraphrase - unrelated) | n/a | 0.301961 |

## Timing and repeatability

Per-chunk embedding used a warm encoder, one text per call (`batch_size=1`); model initialization is excluded. Across 15 samples: mean `0.120368s`, median `0.118597s`, p95 `0.157397s`.

Encoding identical text twice produced cosine `1.000000000000`, maximum component difference `0`, and mean absolute component difference `0`.

The raw pair scores, timing samples, seed, machine details, and model file digest are in `module-eval.json`. Results are CPU- and machine-specific; use the same pinned model, runtime, thread count, and seed when comparing reruns.
