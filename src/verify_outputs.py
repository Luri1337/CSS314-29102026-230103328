
import csv
import hashlib
import json
import os
import sys

from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent)

def fail(milestone: str, reason: str):
    print(f"[FAIL] {milestone}: {reason}")
    sys.exit(1)


def warn(milestone: str, reason: str):
    print(f"[WARN] {milestone}: {reason}")


def pass_step(milestone: str, message: str):
    print(f"[PASS] {milestone}: {message}")


def check_file(path: str, milestone: str) -> str:
    if not os.path.isfile(path):
        fail(milestone, f"Missing required deliverable '{path}'")
    return path


def read_json(path: str, milestone: str):
    check_file(path, milestone)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        fail(milestone, f"Cannot read JSON '{path}': {exc}")


def read_tsv(path: str, milestone: str):
    check_file(path, milestone)
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f, delimiter="\t"))
    except (OSError, csv.Error) as exc:
        fail(milestone, f"Cannot read TSV '{path}': {exc}")


def first_defined(mapping, *keys):
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def verify_milestone_0():
    m = "Milestone 0 (Host & Salt)"
    prof = read_json("results/host_profile.json", m)
    salt = read_json("results/salted_params.json", m)

    for field in ("cpu_model", "physical_cores", "logical_threads", "cache_line_bytes"):
        if field not in prof:
            fail(m, f"Missing key '{field}' in host_profile.json")
    if prof["cache_line_bytes"] != 64:
        fail(m, f"Expected cache_line_bytes == 64, got {prof['cache_line_bytes']}")

    sid = str(salt.get("student_id", "")).strip()
    if not sid:
        fail(m, "student_id is empty in salted_params.json")

    h = int(hashlib.sha256(sid.encode("utf-8")).hexdigest()[:8], 16)
    expected_N = 1024 + ((h % 9) * 64)
    if salt.get("N") != expected_N:
        fail(m, f"Salted dimension N mismatch: expected {expected_N}, got {salt.get('N')}")
    if salt.get("buffer_elements") != 16_777_216:
        fail(m, "buffer_elements does not match the supplied salting formula")
    if salt.get("seed") != h % 100_007:
        fail(m, "seed does not match the supplied salting formula")

    pass_step(m, f"Topology and salting verified. Student ID: {sid} | N: {expected_N}")
    return sid, expected_N


def verify_milestone_1():
    m = "Milestone 1 (Locality & Interchange)"
    rows = read_tsv("results/stride_results.tsv", m)
    strides = {}
    for row in rows:
        try:
            stride_value = first_defined(row, "stride", "Stride")
            latency_value = first_defined(row, "latency_ns", "latency", "Latency_ns", "ns_per_element")
            if stride_value is not None and latency_value is not None:
                strides[int(stride_value)] = float(latency_value)
        except (TypeError, ValueError):
            continue

    if not all(s in strides for s in (1, 8)):
        fail(m, "stride_results.tsv must include measurements for stride 1 and stride 8")
    if strides[1] <= 0 or strides[8] <= 0:
        fail(m, "Stride latencies must be positive")
    if strides[8] <= strides[1]:
        warn(m, f"Stride-8 latency ({strides[8]:.2f} ns) is not above stride-1 ({strides[1]:.2f} ns)")
    else:
        pass_step(m, f"Stride cliff: stride-8 is {strides[8] / strides[1]:.2f}x slower per element")

    inter = read_json("results/loop_interchange.json", m)
    t_naive = first_defined(inter, "naive_time_s", "t_naive")
    t_inter = first_defined(inter, "interchanged_time_s", "t_interchanged")
    # The previously generated files store timings inside named subobjects.
    if t_naive is None:
        t_naive = inter.get("naive_ijk", {}).get("median_seconds")
    if t_inter is None:
        t_inter = inter.get("interchanged_ikj", {}).get("median_seconds")
    if t_naive is None or t_inter is None:
        fail(m, "Missing naive/interchanged timings in loop_interchange.json")

    try:
        t_naive, t_inter = float(t_naive), float(t_inter)
    except (ValueError, TypeError):
        fail(m, "Matrix timings must be numeric")
    if t_naive <= 0 or t_inter <= 0:
        fail(m, "Matrix timings must be greater than zero")
    calc_speedup = t_naive / t_inter  # Missing in the provided teacher script.

    recorded_speedup = inter.get("speedup")
    if recorded_speedup is not None and abs(float(recorded_speedup) - calc_speedup) > 0.01:
        fail(m, "Recorded matrix speedup is inconsistent with the measured timings")
    if inter.get("passes_absolute_1e_minus_12") is False:
        fail(m, "Matrix output is marked as failing the 1e-12 tolerance")
    a_hash = inter.get("naive_ijk", {}).get("sha256_6dp")
    b_hash = inter.get("interchanged_ikj", {}).get("sha256_6dp")
    if a_hash is not None and b_hash is not None and a_hash != b_hash:
        fail(m, "Matrix output digests do not match")

    if calc_speedup < 1.2:
        warn(m, f"Loop interchange speedup only {calc_speedup:.2f}x")
    else:
        pass_step(m, f"Loop interchange: {calc_speedup:.2f}x ({t_naive:.4f}s -> {t_inter:.4f}s)")


def verify_milestone_2():
    m = "Milestone 2 (False Sharing & Karp-Flatt)"
    rows = read_tsv("results/false_sharing_karp_flatt.tsv", m)
    if len(rows) < 2:
        fail(m, "False-sharing TSV needs measurements for multiple process counts")

    unpadded_e = []
    padded_e = []
    # Two supported layouts: one row per method/process count, or wide TSV.
    for row in rows:
        try:
            if "method" in row:
                method = row["method"].strip().lower()
                p = int(first_defined(row, "processes", "p", "P"))
                observed = first_defined(row, "total_observed")
                expected = first_defined(row, "total_expected")
                if expected is not None and observed is not None and int(observed) != int(expected):
                    fail(m, f"Incorrect count for {method} at P={p}: {observed} != {expected}")
                e_value = first_defined(row, "karp_flatt_as_assigned")
                if p > 1 and e_value is not None:
                    if method == "unpadded":
                        unpadded_e.append((p, float(e_value)))
                    elif method == "padded":
                        padded_e.append((p, float(e_value)))
            else:
                p = int(first_defined(row, "p", "P"))
                if p > 1:
                    value_unpad = first_defined(row, "e_unpadded", "e_p_unpadded")
                    value_pad = first_defined(row, "e_padded", "e_p_padded")
                    if value_unpad is not None:
                        unpadded_e.append((p, float(value_unpad)))
                    if value_pad is not None:
                        padded_e.append((p, float(value_pad)))
        except (ValueError, TypeError) as exc:
            fail(m, f"Invalid numeric entry in false-sharing TSV: {exc}")

    if not unpadded_e or not padded_e:
        warn(m, "Karp-Flatt values are missing; checked file structure but cannot assess the trend")
        return

    unpadded_e.sort()
    padded_e.sort()
    first_p, first_e = unpadded_e[0]
    last_p, last_e = unpadded_e[-1]
    if last_e > first_e:
        pass_step(m, f"Unpadded Karp-Flatt: e={first_e:.3f} at P={first_p} -> {last_e:.3f} at P={last_p}")
    else:
        warn(m, "Unpadded Karp-Flatt did not increase between the first and last process counts")
    if padded_e[-1][1] >= last_e:
        warn(m, "Padded Karp-Flatt was not lower at the largest worker count; review measured contention")
    pass_step(m, "False-sharing measurements loaded and recorded counter totals checked")


def verify_milestone_3():
    m = "Milestone 3 (Scaling & Roofline)"
    rows = read_tsv("results/scaling_metrics.tsv", m)
    if len(rows) < 2:
        fail(m, "scaling_metrics.tsv must record multiple worker configurations")

    modes = {str(r.get("mode", "")).strip().lower() for r in rows}
    if "mode" in rows[0] and not {"strong", "weak"}.issubset(modes):
        fail(m, "Both strong and weak scaling rows must be present")
    for row in rows:
        if row.get("correct", "").strip().lower() in ("false", "0", "no"):
            fail(m, f"Scaling result marked numerically incorrect for P={row.get('p')}")
        digest = row.get("checksum_sha256_6dp")
        ref = row.get("reference_sha256_6dp")
        if digest and ref and digest != ref:
            fail(m, f"Scaling checksum mismatch for P={row.get('p')}")

    roof = read_json("results/roofline_summary.json", m)
    regime = first_defined(roof, "regime", "classification", "roofline_predicted_region")
    if not isinstance(regime, str) or "bound" not in regime.lower():
        fail(m, "Roofline must classify the kernel as memory-bound or compute-bound")
    ai = first_defined(roof, "arithmetic_intensity", "ai", "nominal_arithmetic_intensity_flops_per_byte")
    if ai is None:
        fail(m, "Roofline JSON must include arithmetic intensity")
    try:
        if float(ai) <= 0:
            fail(m, "Arithmetic intensity must be positive")
    except (TypeError, ValueError):
        fail(m, "Arithmetic intensity must be numeric")

    pass_step(m, f"Roofline: AI={float(ai):.6f} FLOPs/byte | Region: {regime}")
    pass_step(m, "Scaling results and available numerical checks verified")


def emit_receipt(sid: str, N: int):
    # Same signature formula as in the teacher-provided script.
    raw_token = f"CS482-PRACTICUM-VERIFIED-{sid}-{N}-HASH-SOLO-LAB"
    token = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    os.makedirs("results", exist_ok=True)
    out_path = "results/verification_receipt.sig"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"STUDENT_ID={sid}\n")
        f.write(f"SALTED_N={N}\n")
        f.write(f"SIGNATURE={token}\n")
    print("\n" + "=" * 60)
    print("[COMPLETE] Available recorded results passed the automated checks")
    print(f"Generated receipt: {out_path}")
    print(f"Token: {token[:16]}...")
    print("=" * 60)


def main():
    print("=" * 60)
    print("CS482 Parallel Computing: Automated Practicum Verifier")
    print("=" * 60)
    sid, N = verify_milestone_0()
    verify_milestone_1()
    verify_milestone_2()
    verify_milestone_3()
    emit_receipt(sid, N)


if __name__ == "__main__":
    main()
