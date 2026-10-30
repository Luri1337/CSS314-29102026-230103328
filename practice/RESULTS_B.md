# CS482 Practice Lab - Variant B - Empirical Results

**Student ID:** 230103328  
**OS:** Windows-11-10.0.26300-SP0  
**CPU details:** AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD  
**Logical cores:** 12  
**Python:** 3.14.0  
**Last updated:** 2026-10-30T17:20:55+05:00  
**Worker counts:** 1, 2, 4, 8

## Benchmark measurements

| Configuration | T1 (s) | T2 (s) | T4 (s) | T8 (s) | S8 | e(2) | e(8) | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A: Micro (chunksize=1) | 171.798 | 173.342 | 189.383 | 173.520 | 0.990 | 1.0180 | 1.0115 | Dispatch overhead: at p=8, micro/coarse runtime ratio = 40.77x |
| A: Coarse (chunksize=10,000) | 19.974 | 10.972 | 6.147 | 4.256 | 4.693 | 0.0986 | 0.1007 | Coarse chunks: Karp-Flatt e(2/4/8) = 0.0986/0.0770/0.1007 |
| B: Queue Choke | 8.606 | 45.905 | 70.564 | 95.479 | 0.090 | 9.6677 | 12.5360 | Rising IPC contention; T8 > T1 |
| C: Buffered Batch | 1.619 | 1.036 | 0.867 | 0.835 | 1.939 | 0.2793 | 0.4466 | Buffered IPC; S8=1.94x, e(8)=0.4466 |

## Detailed scaling

Speedup = T1/Tp; Efficiency = Speedup/p × 100%; Karp-Flatt e(p) = (p × Tp/T1 - 1)/(p - 1), for p >= 2.

### A: Micro (chunksize=1)

| Workers | Runtime (s) | Speedup | Efficiency | e(p) |
|---:|---:|---:|---:|---:|
| 1 | 171.798289 | 1.000x | 100.00% | — |
| 2 | 173.341637 | 0.991x | 49.55% | 1.01797 |
| 4 | 189.382526 | 0.907x | 22.68% | 1.13647 |
| 8 | 173.520048 | 0.990x | 12.38% | 1.01145 |

### A: Coarse (chunksize=10,000)

| Workers | Runtime (s) | Speedup | Efficiency | e(p) |
|---:|---:|---:|---:|---:|
| 1 | 19.974456 | 1.000x | 100.00% | — |
| 2 | 10.972196 | 1.820x | 91.02% | 0.09862 |
| 4 | 6.146527 | 3.250x | 81.24% | 0.07696 |
| 8 | 4.256339 | 4.693x | 58.66% | 0.10067 |

### B: Queue Choke

| Workers | Runtime (s) | Speedup | Efficiency | e(p) |
|---:|---:|---:|---:|---:|
| 1 | 8.606344 | 1.000x | 100.00% | — |
| 2 | 45.905025 | 0.187x | 9.37% | 9.66772 |
| 4 | 70.564110 | 0.122x | 3.05% | 10.59877 |
| 8 | 95.478956 | 0.090x | 1.13% | 12.53602 |

### C: Buffered Batch

| Workers | Runtime (s) | Speedup | Efficiency | e(p) |
|---:|---:|---:|---:|---:|
| 1 | 1.619499 | 1.000x | 100.00% | — |
| 2 | 1.035938 | 1.563x | 78.17% | 0.27933 |
| 4 | 0.866617 | 1.869x | 46.72% | 0.38015 |
| 8 | 0.835251 | 1.939x | 24.24% | 0.44657 |

## Buffered-versus-unbuffered throughput

Different work volumes: queue=400,000, buffered=10,000,000. Compare items/s rather than raw runtime.

| Workers | Unbuffered items/s | Buffered items/s | Throughput improvement |
|---:|---:|---:|---:|
| 1 | 46,477 | 6,174,748 | 132.86x |
| 2 | 8,714 | 9,653,088 | 1107.81x |
| 4 | 5,669 | 11,539,120 | 2035.62x |
| 8 | 4,189 | 11,972,453 | 2857.79x |

## Verification and interpretation

- Experiment A: All Collatz checksums must match across 8 configurations.
- Experiment B: All Queue result checksums are checked against expected sums.
- Experiment C: All buffered checksums are checked against expected sums.
- Handout targets (such as e(8) <= 0.05) are *expectations*, not fixed outputs. The results above are measurements from this machine and can differ.

## Execution parameters

- Experiment A: 1,000,000 Collatz inputs; chunksize=1 vs 10,000.
- Experiment B: 400,000 individual Queue.put calls (total over all workers).
- Experiment C: 10,000,000 values, buffered in batches of 10,000.
- Runtime includes process startup, work and result collection, as in the handout.
