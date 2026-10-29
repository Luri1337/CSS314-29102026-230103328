"""Milestone 1.2: Identical matrix multiplication with ijk and ikj order."""
from __future__ import annotations
import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
import numpy as np
from salt import ROOT, read_params


def ijk_python(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = a.shape[0]
    a_flat = a.ravel()
    b_flat = b.ravel()
    c = np.zeros((n, n), dtype=np.float64)
    c_flat = c.ravel()
    for i in range(n):
        base = i * n
        for j in range(n):
            total = 0.0
            for k in range(n):
                total += a_flat[base + k] * b_flat[k*n + j]
            c_flat[base + j] = total
    return c


def ikj_python(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = a.shape[0]
    a_flat = a.ravel()
    b_flat = b.ravel()
    c = np.zeros((n, n), dtype=np.float64)
    c_flat = c.ravel()
    for i in range(n):
        base = i * n
        for k in range(n):
            aik = a_flat[base + k]
            brow = k * n
            for j in range(n):
                c_flat[base + j] += aik * b_flat[brow + j]
    return c


def choose_backend(backend: str):
    if backend in ('auto', 'numba'):
        try:
            from numba import njit
        except ImportError:
            if backend == 'numba':
                raise SystemExit('Numba requested but not installed. pip install numba')
        else:
            # JIT compile the same loops, rather than using BLAS (which would hide locality).
            return njit(ijk_python), njit(ikj_python), 'numba'
    return ijk_python, ikj_python, 'python'


def digest(matrix: np.ndarray) -> str:
    rounded = np.round(matrix, decimals=6)
    return hashlib.sha256(rounded.astype('<f8').tobytes()).hexdigest()


def benchmark(m: int, seed: int, repeats: int, backend: str) -> dict:
    if m <= 0:
        raise ValueError('m must be > 0')
    rng = np.random.default_rng(seed)
    a = rng.random((m, m), dtype=np.float64)
    b = rng.random((m, m), dtype=np.float64)
    naive, improved, selected = choose_backend(backend)
    if selected == 'python' and m >= 512:
        print('WARNING: Python 3-level loops can take many minutes. Install numba for CPU benchmarks.')
    # JIT warm-up/compilation not part of the timing; for pure Python run no warm-up.
    if selected == 'numba':
        naive(a[:2, :2].copy(), b[:2, :2].copy())
        improved(a[:2, :2].copy(), b[:2, :2].copy())
    stats = {}
    results = {}
    for label, fn in [('naive_ijk', naive), ('interchanged_ikj', improved)]:
        durations = []
        result = None
        for j in range(repeats):
            start = time.perf_counter_ns()
            result = fn(a, b)
            elapsed = time.perf_counter_ns() - start
            durations.append(elapsed)
            print(f'{label}: run {j+1}/{repeats}: {elapsed / 1e9:.3f}s')
        stats[label] = {'median_seconds': statistics.median(durations) / 1e9,
                        'per_run_ns': durations, 'sha256_6dp': digest(result)}
        results[label] = result
    max_abs = float(np.max(np.abs(results['naive_ijk'] - results['interchanged_ikj'])))
    max_ref = float(np.max(np.abs(results['naive_ijk'] - a @ b)))
    # Different summation orders imply floating point roundoff; see rubric tolerance.
    out = {
        'matrix_dimension_m': m,
        'seed': seed,
        'backend': selected,
        'repeats': repeats,
        'naive_ijk': stats['naive_ijk'],
        'interchanged_ikj': stats['interchanged_ikj'],
        'speedup': stats['naive_ijk']['median_seconds'] / stats['interchanged_ikj']['median_seconds'],
        'max_abs_difference': max_abs,
        'max_abs_vs_numpy_reference': max_ref,
        'passes_absolute_1e_minus_12': max_abs <= 1e-12,
    }
    outfile = ROOT / 'results' / 'loop_interchange.json'
    outfile.parent.mkdir(exist_ok=True)
    outfile.write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(f'Speedup: {out["speedup"]:.3f}x; max |delta|: {max_abs:.3e}')
    print('Wrote', outfile)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--m', type=int, default=None, help='Override M=N//2 ONLY for smoke testing')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--backend', choices=['auto', 'python', 'numba'], default='auto')
    args = parser.parse_args()
    if args.repeats <= 0:
        parser.error('repeats must be positive')
    params = read_params()
    benchmark(args.m or params['N'] // 2, params['seed'], args.repeats, args.backend)

if __name__ == '__main__':
    main()
