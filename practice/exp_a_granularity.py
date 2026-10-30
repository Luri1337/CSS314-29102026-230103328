import multiprocessing as mp
import time

STUDENT_ID = 230103328
WORKERS = (1, 2, 4, 8)
TOTAL_ITEMS = 1_000_000
CHUNK_SIZES = (1, 10_000)


def collatz_steps(n):
    steps = 0
    while n > 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        steps += 1
    return steps


def run_granularity(workers, total_items=TOTAL_ITEMS, chunk_size=1):
    if workers < 1 or total_items < 1 or chunk_size < 1:
        raise ValueError("workers, total_items and chunk_size must be positive")
    numbers = range(1, total_items + 1)
    start = time.perf_counter()
    # Using processes (not Python threads) avoids the GIL for this CPU-bound task.
    # Pool setup and scheduling are included, exactly as in the handout.
    with mp.get_context("spawn").Pool(processes=workers) as pool:
        result_sum = sum(pool.imap(collatz_steps, numbers, chunksize=chunk_size))
    return time.perf_counter() - start, result_sum


def analyze(runtimes):
    baseline = runtimes[1]
    return {p: (baseline / runtimes[p],
                None if p == 1 else (p * runtimes[p] / baseline - 1) / (p - 1))
            for p in sorted(runtimes)}


def main():
    print(f"Experiment A | Student ID: {STUDENT_ID} | {TOTAL_ITEMS:,} Collatz tasks")
    checksums = {}
    for chunk_size in CHUNK_SIZES:
        runtimes = {}
        print(f"\nChunksize = {chunk_size:,}")
        print("Workers | Time (s) | Speedup | Efficiency | Karp-Flatt e(p) | Checksum")
        for p in WORKERS:
            seconds, checksum = run_granularity(p, chunk_size=chunk_size)
            checksums[(chunk_size, p)] = checksum
            runtimes[p] = seconds
            speedup = runtimes[1] / seconds
            efficiency = speedup / p * 100 if p > 1 else 100.0
            e = "N/A" if p == 1 else f"{(p * seconds / runtimes[1] - 1) / (p - 1):.4f}"
            print(f"{p:7d} | {seconds:8.3f} | {speedup:7.3f}x | {efficiency:9.1f}% | {e:15} | {checksum}", flush=True)
    assert len(set(checksums.values())) == 1, "Mismatched results across pool configurations"
    print("VERIFICATION: PASS - all Collatz checksums match")


if __name__ == "__main__":
    mp.freeze_support()
    main()
