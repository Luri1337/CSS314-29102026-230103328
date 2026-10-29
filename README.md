# CS482 laboratory submission

Run the experiments on your own physical machine (Python 3.10+, NumPy; Numba optional for faster dense kernel):

```bash
python -m pip install numpy numba
python src/profile_env.py --student-id YOUR_ID
python src/stride_bench.py
python src/dense_kernel.py
python src/false_sharing.py
python src/scaling_study.py --memory-bandwidth-gbps YOUR_VERIFIED_GBPS --peak-gflops YOUR_VERIFIED_GFLOPS
```

Replace the bandwidth and GFLOPS placeholders with verified specifications for your hardware. Follow the PDF's Git checkpoints and tags **M0-ENV**, **M1-LOCALITY**, **M2-SHARING**, **M3-SCALING**, **M4-FINAL**, committing each milestone as it is completed. To finish, run the professor-provided `verify_outputs.py` (not supplied with the PDF). It must produce `results/verification_receipt.sig` after numerical verification.

**Findings:** After running the experiments on your machine, replace this paragraph with one short paragraph reporting your measured stride latency change, i-j-k vs. i-k-j speedup, false-sharing slowdown and padding/privatization improvements, strong/weak scaling results, and Roofline classification. Do not invent results.

The assignment explicitly forbids AI code generation for assessed submissions. These scripts are a reference implementation; verify course integrity rules before using them for submission.
