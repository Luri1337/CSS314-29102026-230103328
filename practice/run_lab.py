
import multiprocessing as mp
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

from exp_a_granularity import CHUNK_SIZES, TOTAL_ITEMS as A_ITEMS, WORKERS, run_granularity
from exp_b_queue import TOTAL_ITEMS as B_ITEMS, run_queue_benchmark
from exp_c_buffered import BATCH_SIZE, TOTAL_ITEMS as C_ITEMS, run_buffered

STUDENT_ID = 230103328
BASE = Path(__file__).resolve().parent
REPORT_PATH = BASE / "RESULTS_B.md"
OUTPUT_PATH = BASE / "lab_output.txt"


def speedup(times, p):
    return times[1] / times[p]


def efficiency(times, p):
    return speedup(times, p) / p * 100


def karp_flatt(times, p):
    if p == 1:
        return None
    return (p * times[p] / times[1] - 1) / (p - 1)


def fmt(number, digits=3):
    return "—" if number is None else f"{number:.{digits}f}"


def analysis_text(key, results):
    if key not in results:
        return "Not yet measured on this machine"
    times = results[key]
    if key == "A_micro":
        if "A_coarse" not in results:
            return "Fine-grained tasks; coarse-grained comparison pending"
        coarse = results["A_coarse"]
        ratio = times[8] / coarse[8]
        return f"Dispatch overhead: at p=8, micro/coarse runtime ratio = {ratio:.2f}x"
    if key == "A_coarse":
        values = [karp_flatt(times, p) for p in (2, 4, 8)]
        return "Coarse chunks: Karp-Flatt e(2/4/8) = " + "/".join(fmt(v, 4) for v in values)
    if key == "B_queue":
        rising = all(karp_flatt(times, a) < karp_flatt(times, b) for a, b in [(2, 4), (4, 8)])
        return ("Rising IPC contention" if rising else "Non-monotonic IPC contention (check measured data)") + (
            "; T8 > T1" if times[8] > times[1] else "; T8 <= T1")
    if key == "C_buffered":
        return f"Buffered IPC; S8={speedup(times, 8):.2f}x, e(8)={karp_flatt(times, 8):.4f}"
    return ""


def render_report(results):
    labels = [
        ("A_micro", "A: Micro (chunksize=1)"),
        ("A_coarse", "A: Coarse (chunksize=10,000)"),
        ("B_queue", "B: Queue Choke"),
        ("C_buffered", "C: Buffered Batch"),
    ]
    lines = [
        "# CS482 Practice Lab - Variant B - Empirical Results",
        "",
        f"**Student ID:** {STUDENT_ID}  ",
        f"**OS:** {platform.platform()}  ",
        f"**CPU details:** {platform.processor() or platform.machine()}  ",
        f"**Logical cores:** {os.cpu_count()}  ",
        f"**Python:** {platform.python_version()}  ",
        f"**Last updated:** {datetime.now().astimezone().isoformat(timespec='seconds')}  ",
        "**Worker counts:** 1, 2, 4, 8",
        "",
        "## Benchmark measurements",
        "",
        "| Configuration | T1 (s) | T2 (s) | T4 (s) | T8 (s) | S8 | e(2) | e(8) | Verdict |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, label in labels:
        times = results.get(key)
        values = ([fmt(times[p]) for p in WORKERS] +
                  [fmt(speedup(times, 8), 3), fmt(karp_flatt(times, 2), 4), fmt(karp_flatt(times, 8), 4)]
                  if times else ["Pending"] * 7)
        lines.append("| " + " | ".join([label] + values + [analysis_text(key, results)]) + " |")
    lines += [
        "", "## Detailed scaling", "",
        "Speedup = T1/Tp; Efficiency = Speedup/p × 100%; "
        "Karp-Flatt e(p) = (p × Tp/T1 - 1)/(p - 1), for p >= 2.", "",
    ]
    for key, label in labels:
        lines += [f"### {label}", ""]
        if key not in results:
            lines += ["Not yet measured on this computer.", ""]
            continue
        times = results[key]
        lines += ["| Workers | Runtime (s) | Speedup | Efficiency | e(p) |",
                  "|---:|---:|---:|---:|---:|"]
        for p in WORKERS:
            lines.append(f"| {p} | {times[p]:.6f} | {speedup(times, p):.3f}x | "
                         f"{efficiency(times, p):.2f}% | {fmt(karp_flatt(times, p), 5)} |")
        lines.append("")
    if "B_queue" in results and "C_buffered" in results:
        b, c = results["B_queue"], results["C_buffered"]
        lines += ["## Buffered-versus-unbuffered throughput", "",
                  "Different work volumes: queue=400,000, buffered=10,000,000. "
                  "Compare items/s rather than raw runtime.", "",
                  "| Workers | Unbuffered items/s | Buffered items/s | Throughput improvement |",
                  "|---:|---:|---:|---:|"]
        for p in WORKERS:
            old_rate = B_ITEMS / b[p]
            new_rate = C_ITEMS / c[p]
            lines.append(f"| {p} | {old_rate:,.0f} | {new_rate:,.0f} | {new_rate / old_rate:.2f}x |")
        lines.append("")
    lines += [
        "## Verification and interpretation", "",
        "- Experiment A: All Collatz checksums must match across 8 configurations.",
        "- Experiment B: All Queue result checksums are checked against expected sums.",
        "- Experiment C: All buffered checksums are checked against expected sums.",
        "- Handout targets (such as e(8) <= 0.05) are *expectations*, not fixed outputs. "
        "The results above are measurements from this machine and can differ.",
        "", "## Execution parameters", "",
        f"- Experiment A: {A_ITEMS:,} Collatz inputs; chunksize=1 vs 10,000.",
        f"- Experiment B: {B_ITEMS:,} individual Queue.put calls (total over all workers).",
        f"- Experiment C: {C_ITEMS:,} values, buffered in batches of {BATCH_SIZE:,}.",
        "- Runtime includes process startup, work and result collection, as in the handout.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    results = {}
    # Record output live, so data already printed is retained if a long run is stopped.
    with OUTPUT_PATH.open("w", encoding="utf-8") as output:
        def log(message=""):
            print(message, flush=True)
            output.write(message + "\n")
            output.flush()

        log(f"CS482 Variant B | Student ID: {STUDENT_ID}")
        log(f"OS: {platform.platform()}")
        log(f"CPU: {platform.processor() or platform.machine()}")
        log(f"Logical cores: {os.cpu_count()} | Pool CPU count: {mp.cpu_count()}")
        log("Python: " + platform.python_version())
        log("Parallel workers: 1, 2, 4, 8 | multiprocessing spawn")
        log("Timings are measured live on this machine (seconds).")
        render_report(results)

        reference_collatz_checksum = None
        for chunk_size, key in ((1, "A_micro"), (10_000, "A_coarse")):
            log(f"\nExperiment A - Collatz, chunksize={chunk_size:,}, total={A_ITEMS:,}")
            log("P | Runtime (s) | Speedup | Efficiency | Karp-Flatt | Checksum")
            times = {}
            checksums = []
            for p in WORKERS:
                elapsed, checksum = run_granularity(p, chunk_size=chunk_size)
                times[p] = elapsed
                checksums.append(checksum)
                log(f"{p} | {elapsed:.6f} | {speedup(times, p):.3f}x | "
                    f"{efficiency(times, p):.2f}% | {fmt(karp_flatt(times, p), 5)} | {checksum}")
            if len(set(checksums)) != 1:
                raise AssertionError("Experiment A Collatz checksums differ")
            if reference_collatz_checksum is not None and checksums[0] != reference_collatz_checksum:
                raise AssertionError("Experiment A fine/coarse Collatz checksums differ")
            reference_collatz_checksum = checksums[0]
            results[key] = times
            log("PASS: matching Collatz checksums")
            render_report(results)

        for label, key, runner, total in (
            ("B - Unbuffered Queue", "B_queue", run_queue_benchmark, B_ITEMS),
            ("C - Buffered Queue", "C_buffered", run_buffered, C_ITEMS),
        ):
            log(f"\nExperiment {label} | {total:,} total items")
            log("P | Runtime (s) | Speedup | Efficiency | Karp-Flatt | Checksum")
            times = {}
            for p in WORKERS:
                elapsed, checksum = runner(p)
                times[p] = elapsed
                log(f"{p} | {elapsed:.6f} | {speedup(times, p):.3f}x | "
                    f"{efficiency(times, p):.2f}% | {fmt(karp_flatt(times, p), 5)} | {checksum}")
            results[key] = times
            log("PASS: checksums verified")
            render_report(results)

        log("\nDONE: RESULTS_B.md and lab_output.txt generated on this machine.")
        log("Commit all experiment scripts and RESULTS_B.md to branch variant-b-230103328.")


if __name__ == "__main__":
    mp.freeze_support()
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted: any completed experiment remains in RESULTS_B.md.", file=sys.stderr)
        raise SystemExit(130)
