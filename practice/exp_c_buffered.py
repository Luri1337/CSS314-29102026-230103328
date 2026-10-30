
import multiprocessing as mp
import time

STUDENT_ID = 230103328
WORKERS = (1, 2, 4, 8)
TOTAL_ITEMS = 10_000_000
BATCH_SIZE = 10_000


def buffered_worker(out_queue, items_per_worker, batch_size=BATCH_SIZE):
    buffer = []
    try:
        for i in range(items_per_worker):
            buffer.append(i % 7)
            if len(buffer) >= batch_size:
                out_queue.put(sum(buffer))  # One IPC message per 10,000 elements.
                buffer.clear()
        if buffer:
            out_queue.put(sum(buffer))
        out_queue.put(None)  # Per-worker completion sentinel.
    finally:
        # Explicitly let the Queue's feeder finish before the process exits.
        out_queue.close()
        out_queue.join_thread()


def run_buffered(p, total_items=TOTAL_ITEMS, batch_size=BATCH_SIZE):
    if p < 1 or total_items < 1 or batch_size < 1:
        raise ValueError("Worker count, total_items and batch_size must be positive")
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    quotas = [total_items // p + (1 if i < total_items % p else 0) for i in range(p)]
    workers = [ctx.Process(target=buffered_worker, args=(queue, count, batch_size))
               for count in quotas]

    start = time.perf_counter()
    try:
        for worker in workers:
            worker.start()
        total_sum = 0
        finished = 0
        while finished < p:
            item = queue.get()
            if item is None:
                finished += 1
            else:
                total_sum += item
        for worker in workers:
            worker.join()
        if any(worker.exitcode != 0 for worker in workers):
            raise RuntimeError("A buffered worker exited with an error")
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()
        queue.close()
        queue.join_thread()
    elapsed = time.perf_counter() - start
    expected = sum((n // 7) * 21 + sum(range(n % 7)) for n in quotas)
    if total_sum != expected:
        raise AssertionError(f"Buffered checksum mismatch: {total_sum} vs {expected}")
    return elapsed, total_sum


def main():
    print(f"Experiment C | Student ID: {STUDENT_ID} | {TOTAL_ITEMS:,} items | Batch {BATCH_SIZE:,}")
    print("Workers | Time (s) | Speedup | Efficiency | Karp-Flatt e(p) | Checksum")
    runtimes = {}
    for p in WORKERS:
        seconds, checksum = run_buffered(p)
        runtimes[p] = seconds
        speedup = runtimes[1] / seconds
        efficiency = speedup / p * 100
        e = "N/A" if p == 1 else f"{(p * seconds / runtimes[1] - 1) / (p - 1):.4f}"
        print(f"{p:7d} | {seconds:8.3f} | {speedup:7.3f}x | {efficiency:9.1f}% | {e:15} | {checksum}", flush=True)
    print("VERIFICATION: PASS - all buffered checksums correct")


if __name__ == "__main__":
    mp.freeze_support()
    main()
