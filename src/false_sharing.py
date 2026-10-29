"""Milestone 2: Deliberately reproduce false sharing, then pad or privatize."""
from __future__ import annotations
import argparse
import csv
import ctypes
import multiprocessing as mp
import statistics
import time
from salt import ROOT

PROCESSES = (1, 2, 4, 8)
METHODS = ('unpadded', 'padded', 'privatized')


def worker(shared, wid: int, iterations: int, method: str, commit_lock):
    if method == 'privatized':
        local = 0
        for _ in range(iterations):
            local += 1
        # Exactly one synchronized write per process.
        with commit_lock:
            shared[wid * 8] = local
    else:
        index = wid if method == 'unpadded' else wid * 8
        for _ in range(iterations):
            shared[index] += 1


def trial(ctx, p: int, k: int, method: str) -> tuple[int, int]:
    # lock=False matters: the shared wrapper's global lock would create a
    # software bottleneck unrelated to MESI cache-line invalidations.
    count = 8 if method == 'unpadded' else 8 * p
    shared = ctx.Array(ctypes.c_int64, count, lock=False)
    commit_lock = ctx.Lock()
    procs = [ctx.Process(target=worker, args=(shared, wid, k, method, commit_lock))
             for wid in range(p)]
    t0 = time.perf_counter_ns()
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join()
    elapsed = time.perf_counter_ns() - t0
    failures = [proc.exitcode for proc in procs if proc.exitcode != 0]
    if failures:
        raise RuntimeError(f'Worker processes failed: {failures}')
    total = sum(shared)
    if total != p*k:
        raise AssertionError(f'{method} P={p}: expected {p*k} increments, got {total}')
    return elapsed, total


def benchmark(procs: list[int], k: int, repeats: int) -> None:
    if not procs or 1 not in procs:
        raise ValueError('Must include P=1 baseline')
    if max(procs) > 8:
        raise ValueError('PDF specifies a maximum of 8 workers')
    ctx = mp.get_context('spawn')
    records = []
    baseline = {}
    for method in METHODS:
        for p in procs:
            times = []
            total = 0
            for r in range(repeats):
                elapsed, total = trial(ctx, p, k, method)
                times.append(elapsed)
                print(f'{method:11} P={p}, repeat {r+1}/{repeats}, elapsed={elapsed/1e9:.3f}s')
            median = statistics.median(times)
            if p == 1:
                baseline[method] = median
            t1 = baseline[method]
            # This is the literal Karp-Flatt formula specified in the PDF.
            # WARNING: PDF assigns K to EACH process, so total work = P*K,
            # violating Karp-Flatt's fixed-work assumption. See README.
            speedup = t1 / median
            e = ((p * median / t1) - 1) / (p-1) if p > 1 else None
            records.append({
                'method': method, 'processes': p, 'iterations_per_process': k,
                'total_expected': p*k, 'total_observed': total,
                'median_elapsed_ns': f'{median:.1f}',
                'seconds': f'{median/1e9:.6f}',
                'speedup_T1_over_Tp': f'{speedup:.6f}',
                'relative_throughput_gain_P_T1_over_Tp': f'{p*speedup:.6f}',
                'karp_flatt_as_assigned': '' if e is None else f'{e:.6f}',
                'repeats': repeats,
            })
    file = ROOT / 'results' / 'false_sharing_karp_flatt.tsv'
    file.parent.mkdir(exist_ok=True)
    with file.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]), delimiter='\t')
        w.writeheader()
        w.writerows(records)
    print('Wrote', file)
    print('CAUTION: each process performs K iterations, so P changes total work; see README.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=5_000_000)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--processes', type=int, nargs='+', default=list(PROCESSES))
    a = parser.parse_args()
    if a.iterations <= 0 or a.repeats <= 0 or len(set(a.processes)) != len(a.processes):
        parser.error('positive iterations/repeats and unique process counts required')
    if sorted(a.processes) != a.processes:
        parser.error('process counts must be ascending (starting with 1)')
    benchmark(a.processes, a.iterations, a.repeats)

if __name__ == '__main__':
    main()
