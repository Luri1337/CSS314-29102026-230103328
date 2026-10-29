"""Milestone 3: 2D five-point stencil with shared-memory multi-process workers."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import multiprocessing as mp
from multiprocessing import shared_memory
import statistics
import time
import numpy as np
from salt import ROOT, read_params

_ARRAYS = None
_HANDLES = None


def _pool_initializer(shm0_name: str, shm1_name: str, n: int):
    global _ARRAYS, _HANDLES
    a = shared_memory.SharedMemory(name=shm0_name)
    b = shared_memory.SharedMemory(name=shm1_name)
    _HANDLES = (a, b)  # Keep handles alive for the entire worker lifetime.
    _ARRAYS = (np.ndarray((n, n), dtype=np.float64, buffer=a.buf),
               np.ndarray((n, n), dtype=np.float64, buffer=b.buf))


def _stencil_slice(start: int, end: int, parity: int):
    src, dst = (_ARRAYS if parity == 0 else (_ARRAYS[1], _ARRAYS[0]))
    if start >= end:
        return
    dst[start:end, 1:-1] = 0.2 * (
        src[start:end, 1:-1] + src[start-1:end-1, 1:-1] +
        src[start+1:end+1, 1:-1] + src[start:end, :-2] + src[start:end, 2:]
    )


def _reference(initial: np.ndarray, steps: int) -> np.ndarray:
    src = initial.copy()
    dst = np.zeros_like(src)
    for _ in range(steps):
        dst[1:-1, 1:-1] = 0.2 * (
            src[1:-1, 1:-1] + src[:-2, 1:-1] + src[2:, 1:-1] +
            src[1:-1, :-2] + src[1:-1, 2:]
        )
        src, dst = dst, src
    return src


def sha_6dp(matrix: np.ndarray) -> str:
    return hashlib.sha256(np.round(matrix, 6).astype('<f8').tobytes()).hexdigest()


def _chunks(n: int, p: int) -> list[tuple[int, int]]:
    # Only interior rows; p must be <= n-2.
    return [(1 + (n-2)*i//p, 1 + (n-2)*(i+1)//p) for i in range(p)]


def measure(n: int, p: int, steps: int, repeats: int, seed: int) -> dict:
    initial = np.random.default_rng(seed).random((n, n), dtype=np.float64)
    initial[0, :] = initial[-1, :] = 0.0
    initial[:, 0] = initial[:, -1] = 0.0
    reference = _reference(initial, steps)
    ref_digest = sha_6dp(reference)
    shms = [shared_memory.SharedMemory(create=True, size=initial.nbytes) for _ in range(2)]
    try:
        arrays = [np.ndarray((n, n), dtype=np.float64, buffer=s.buf) for s in shms]
        row_chunks = _chunks(n, p)
        ctx = mp.get_context('spawn')
        with ctx.Pool(p, initializer=_pool_initializer,
                      initargs=(shms[0].name, shms[1].name, n)) as pool:
            durations = []
            for r in range(repeats):
                arrays[0][:] = initial
                arrays[1].fill(0.0)
                t0 = time.perf_counter_ns()
                for step in range(steps):
                    pool.starmap(_stencil_slice, [(start, end, step % 2)
                                                 for start, end in row_chunks])
                elapsed = time.perf_counter_ns() - t0
                final = arrays[steps % 2]
                max_abs = float(np.max(np.abs(final - reference)))
                if max_abs > 1e-12:
                    raise AssertionError(f'Stencil mismatch n={n} p={p}: {max_abs:.3e}')
                if sha_6dp(final) != ref_digest:
                    raise AssertionError('Rounded SHA-256 differs despite numerical tolerance')
                durations.append(elapsed)
                print(f'stencil N={n}, P={p}, repeat {r+1}/{repeats}: {elapsed/1e9:.3f}s')
        return {
            'median_ns': statistics.median(durations), 'run_ns': durations,
            'checksum_sha256_6dp': ref_digest,
            'reference_sha256_6dp': sha_6dp(reference),
            'correct': True,
        }
    finally:
        for s in shms:
            s.close()
            s.unlink()


def _load_bandwidth_from_stride() -> float | None:
    filepath = ROOT / 'results' / 'stride_results.tsv'
    if not filepath.exists():
        return None
    try:
        with filepath.open(newline='', encoding='utf-8') as f:
            rec = next(x for x in csv.DictReader(f, delimiter='\t') if int(x['stride']) == 1)
        # logical GB/s, not DRAM peak bandwidth; never label it "theoretical peak".
        elapsed_s = float(rec['median_elapsed_ns']) / 1e9
        return (int(rec['elements_touched']) * 8 / 1e9) / elapsed_s
    except (OSError, KeyError, ValueError, StopIteration, ZeroDivisionError):
        return None


def process_counts(max_processes: int) -> list[int]:
    result = [1]
    while result[-1]*2 <= max_processes:
        result.append(result[-1]*2)
    return result


def benchmark(n: int, processes: list[int], steps: int, repeats: int,
              seed: int, peak_bw: float | None, peak_flops: float | None):
    outputs = []
    strong = []
    for p in processes:
        r = measure(n, p, steps, repeats, seed)
        strong.append((p, r))
    t1_ns = strong[0][1]['median_ns']
    raw_fractions = []
    for p, r in strong:
        tp_ns = r['median_ns']
        sp = t1_ns/tp_ns
        s = ((1/sp - 1/p)/(1 - 1/p)) if p != 1 else None
        if p > 1:
            raw_fractions.append((p, s))
        outputs.append({
            'mode': 'strong', 'p': p, 'n': n, 'steps': steps,
            'work_cells': (n-2)**2*steps,
            'median_seconds': f'{tp_ns/1e9:.8f}',
            'speedup': f'{sp:.8f}', 'efficiency_pct': f'{100*sp/p:.6f}',
            'amdahl_effective_serial_fraction': '' if s is None else f'{s:.9f}',
            'pdf_weak_scaled_speedup': '',
            'checksum_sha256_6dp': r['checksum_sha256_6dp'],
            'reference_sha256_6dp': r['reference_sha256_6dp'],
            'correct': r['correct'],
        })
    # Least squares of T(P)/T(1) ~= s + (1-s)/P.
    denominator = sum((1 - 1/p)**2 for p, _ in raw_fractions)
    fit_s_raw = (sum((1 - 1/p) * ((1 + s*(p-1))/p - 1/p)
                    for p, s in raw_fractions) / denominator) if denominator else None
    # Above simplifies to weighted average of the per-P Karp-Flatt fractions.
    fit_s = min(1.0, max(0.0, fit_s_raw)) if fit_s_raw is not None else None
    print('Amdahl serial fraction fit:', fit_s)
    weak_results = []
    for p in processes:
        wn = math.ceil(n * math.sqrt(p))
        r = measure(wn, p, steps, repeats, seed)
        wp = (wn-2)**2 * steps
        w1 = (n-2)**2 * steps
        tp_ns = r['median_ns']
        scaled = (p * w1 * t1_ns)/(wp * tp_ns)
        weak_results.append({'p': p, 'dimension': wn, 'median_seconds': tp_ns/1e9,
                             'pdf_scaled_speedup': scaled})
        outputs.append({
            'mode': 'weak', 'p': p, 'n': wn, 'steps': steps,
            'work_cells': wp, 'median_seconds': f'{tp_ns/1e9:.8f}',
            'speedup': f'{t1_ns/tp_ns:.8f}',
            'efficiency_pct': f'{100*t1_ns/tp_ns:.6f}',
            'amdahl_effective_serial_fraction': '',
            'pdf_weak_scaled_speedup': f'{scaled:.8f}',
            'checksum_sha256_6dp': r['checksum_sha256_6dp'],
            'reference_sha256_6dp': r['reference_sha256_6dp'],
            'correct': r['correct'],
        })
    out = ROOT / 'results' / 'scaling_metrics.tsv'
    with out.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(outputs[0]), delimiter='\t')
        w.writeheader()
        w.writerows(outputs)
    # Nominal per-cell traffic = 5 loads + 1 store. Cache-line reuse / write
    # allocate may change actual *DRAM* bytes; this is a naive roofline model.
    flops_per_cell = 5  # four additions + one multiplication
    nominal_bytes_per_cell = 6 * 8
    intensity = flops_per_cell / nominal_bytes_per_cell
    if peak_bw and peak_flops:
        ridge = peak_flops / peak_bw
        predicted = 'memory_bandwidth_bound' if intensity < ridge else 'compute_bound'
        ceiling = min(peak_flops, peak_bw * intensity)
    else:
        ridge, predicted, ceiling = None, 'undetermined_missing_hardware_peaks', None
    summary = {
        'n_base': n, 'processes': processes, 'steps': steps,
        'amdahl_serial_fraction_fit': fit_s,
        'amdahl_raw_serial_fraction_fit': fit_s_raw,
        'amdahl_S_max': (1/fit_s if fit_s and fit_s > 0 else None),
        'gustafson_barsis_model_speedups': ({str(p): p-fit_s*(p-1) for p in processes}
                                              if fit_s is not None else None),
        'weak_scaling_runs': weak_results,
        'flops_per_output_cell': flops_per_cell,
        'nominal_bytes_per_output_cell': nominal_bytes_per_cell,
        'nominal_arithmetic_intensity_flops_per_byte': intensity,
        'important_limitation': 'Nominal 5 loads and 1 store are not measured DRAM traffic; cache reuse and write allocation are ignored.',
        'peak_theoretical_memory_bandwidth_gb_s': peak_bw,
        'peak_theoretical_compute_gflops': peak_flops,
        'measured_stride1_logical_read_gb_s': _load_bandwidth_from_stride(),
        'roofline_ridge_point_flops_per_byte': ridge,
        'roofline_predicted_region': predicted,
        'roofline_predicted_ceiling_gflops': ceiling,
        'pdf_weak_formula_note': 'The PDF formula normalizes by Work(P)/Work(1); with Work(P)~P Work(1), it is approximately a relative runtime/throughput efficiency, NOT the conventional Gustafson scaled speedup.',
    }
    summaryfile = ROOT / 'results' / 'roofline_summary.json'
    summaryfile.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print('Wrote', out)
    print('Wrote', summaryfile)
    if predicted.startswith('undetermined'):
        print('Roofline classification requires user-supplied peak bandwidth and CPU compute GFLOP/s.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--n', type=int, default=None, help='Override salted N for quick tests only')
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--max-procs', type=int, default=None)
    parser.add_argument('--memory-bandwidth-gbps', type=float, default=None,
                        help='Theoretical peak from RAM speed * channels (not an estimate)')
    parser.add_argument('--peak-gflops', type=float, default=None,
                        help='Theoretical peak from CPU frequency, width, SIMD, cores, FMA')
    a = parser.parse_args()
    params = read_params()
    prof = json.loads((ROOT / 'results' / 'host_profile.json').read_text(encoding='utf-8'))
    pmax = a.max_procs or prof.get('physical_cores') or 1
    if pmax < 1 or a.steps < 1 or a.repeats < 1:
        parser.error('max-procs, steps, repeats must be positive')
    if (a.memory_bandwidth_gbps is not None and a.memory_bandwidth_gbps <= 0) or (a.peak_gflops is not None and a.peak_gflops <= 0):
        parser.error('peak memory bandwidth and compute must be positive')
    n = a.n or params['N']
    if n < 4:
        parser.error('n must be >= 4')
    ps = process_counts(min(pmax, n-2))
    benchmark(n, ps, a.steps, a.repeats, params['seed'],
              a.memory_bandwidth_gbps, a.peak_gflops)

if __name__ == '__main__':
    main()
