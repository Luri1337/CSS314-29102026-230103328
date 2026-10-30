
import multiprocessing as mp
import time

STUDENT_ID = 230103328
WORKERS = (1, 2, 4, 8)
TOTAL_ITEMS = 400_000


def queue_worker(out_queue, items_per_worker):
    for i in range(items_per_worker):
        # Every record crosses the IPC channel individually: intentionally slow.
        out_queue.put(i % 7)


def run_queue_benchmark(p, total_items=TOTAL_ITEMS):
    if p < 1 or total_items < 1:
        raise ValueError("Worker count and total_items must be positive")
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    # Handle any non-divisible total exactly, without dropping records.
    quotas = [total_items // p + (1 if i < total_items % p else 0) for i in range(p)]
    workers = [ctx.Process(target=queue_worker, args=(queue, count)) for count in quotas]

    start = time.perf_counter()
    try:
        for worker in workers:
            worker.start()
        received_sum = 0
        for _ in range(total_items):
            received_sum += queue.get()
        for worker in workers:
            worker.join()
        if any(worker.exitcode != 0 for worker in workers):
            raise RuntimeError("A queue worker exited with an error")
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()
        queue.close()
        queue.join_thread()
    elapsed = time.perf_counter() - start
    expected = sum((n // 7) * 21 + sum(range(n % 7)) for n in quotas)
    if received_sum != expected:
        raise AssertionError(f"Queue checksum mismatch: {received_sum} vs {expected}")
    return elapsed, received_sum


def main():
    print(f"Experiment B | Student ID: {STUDENT_ID} | {TOTAL_ITEMS:,} Queue.put calls")
    print("Workers | Time (s) | Speedup | Efficiency | Karp-Flatt e(p) | Checksum")
    runtimes = {}
    for p in WORKERS:
        seconds, checksum = run_queue_benchmark(p)
        runtimes[p] = seconds
        speedup = runtimes[1] / seconds
        efficiency = speedup / p * 100
        e = "N/A" if p == 1 else f"{(p * seconds / runtimes[1] - 1) / (p - 1):.4f}"
        print(f"{p:7d} | {seconds:8.3f} | {speedup:7.3f}x | {efficiency:9.1f}% | {e:15} | {checksum}", flush=True)
    print("VERIFICATION: PASS - all queue checksums correct")


if __name__ == "__main__":
    mp.freeze_support()
    main()
