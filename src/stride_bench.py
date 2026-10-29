"""Milestone 1.1: NumPy/C-level reductions over strided float64 views."""
from __future__ import annotations
import argparse
import csv
import statistics
import time
import numpy as np
from salt import ROOT, read_params

STRIDES = (1, 2, 4, 8, 16, 32, 64, 128)


def benchmark(elements: int, warmups: int, repeats: int) -> None:
    data = np.ones(elements, dtype=np.float64)
    out = ROOT / 'results' / 'stride_results.tsv'
    out.parent.mkdir(exist_ok=True)
    rows = []
    for stride in STRIDES:
        view = data[::stride]
        touches = len(view)
        for _ in range(warmups):
            np.sum(view, dtype=np.float64)
        times = []
        checksum = None
        for _ in range(repeats):
            t0 = time.perf_counter_ns()
            total = float(np.sum(view, dtype=np.float64))
            times.append(time.perf_counter_ns() - t0)
            checksum = total
        if checksum != float(touches):
            raise RuntimeError(f'Incorrect stride reduction for s={stride}: {checksum} != {touches}')
        median = statistics.median(times)
        rows.append({
            'stride': stride, 'elements_touched': touches, 'buffer_elements': elements,
            'median_elapsed_ns': f'{median:.1f}', 'ns_per_element': f'{median/touches:.6f}',
            'read_gb_per_s_logical': f'{touches*8/median:.6f}',
            'checksum': f'{checksum:.0f}', 'warmups': warmups, 'repeats': repeats,
        })
        print(f'stride={stride:3}  touched={touches:>9}  {median/touches:>9.3f} ns/element')
    with out.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    print('Wrote', out)


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--elements', type=int, default=None, help='Use a smaller buffer ONLY for smoke tests')
    args.add_argument('--warmups', type=int, default=5)
    args.add_argument('--repeats', type=int, default=5)
    a = args.parse_args()
    if a.repeats <= 0 or a.warmups < 0:
        args.error('repeats > 0 and warmups >= 0 required')
    benchmark(a.elements or read_params()['buffer_elements'], a.warmups, a.repeats)

if __name__ == '__main__':
    main()
