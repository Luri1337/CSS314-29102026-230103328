"""Milestone 0: Profile actual CPU topology and write salted parameters."""
from __future__ import annotations
import argparse
import ctypes
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from salt import ROOT, get_student_params


def _linux_info() -> dict:
    data: dict = {}
    cpuinfo = Path('/proc/cpuinfo')
    if cpuinfo.is_file():
        raw = cpuinfo.read_text(errors='replace')
        blocks = [b for b in raw.strip().split('\n\n') if b.strip()]
        sections = [dict(line.split(':', 1) for line in block.splitlines() if ':' in line) for block in blocks]
        sections = [{k.strip(): v.strip() for k, v in d.items()} for d in sections]
        if sections:
            first = sections[0]
            data['model'] = first.get('model name', first.get('Hardware', 'unknown'))
            data['cpu_family'] = first.get('cpu family')
            data['model_number'] = first.get('model')
            data['stepping'] = first.get('stepping')
            unique_cores = {(p['physical id'], p['core id']) for p in sections
                            if 'physical id' in p and 'core id' in p}
            if unique_cores:
                data['physical_cores'] = len(unique_cores)
    for p in ('/sys/devices/system/cpu/cpu0/cpufreq/base_frequency',
              '/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq'):
        try:
            khz = int(Path(p).read_text().strip())
            data['reported_frequency_mhz'] = round(khz / 1000, 2)
            data['frequency_source'] = p
            break
        except (OSError, ValueError):
            continue
    entries = []
    cache_dir = Path('/sys/devices/system/cpu/cpu0/cache')
    for index in sorted(cache_dir.glob('index*')):
        try:
            info = {k: (index / k).read_text().strip() for k in
                    ('level', 'type', 'size', 'coherency_line_size')}
            entries.append(info)
        except OSError:
            continue
    data['cache_raw'] = entries
    for c in entries:
        size = _parse_bytes(c['size'])
        level, kind = c['level'], c['type'].lower()
        if level == '1' and kind == 'data':
            data['l1_data_cache_bytes_per_core'] = size
        elif level == '2':
            data['l2_cache_bytes_per_core_or_cluster'] = size
        elif level == '3':
            data['l3_shared_cache_bytes_per_domain'] = size
        if c['coherency_line_size'].isdigit():
            data['cache_line_bytes'] = int(c['coherency_line_size'])
    return data


def _parse_bytes(x: str) -> int:
    match = re.fullmatch(r'\s*(\d+)\s*([KMGT]?)\s*B?\s*', x, re.I)
    if not match:
        raise ValueError(f'Unrecognized cache size {x!r}')
    return int(match.group(1)) * 1024 ** ('', 'K', 'M', 'G', 'T').index(match.group(2).upper())


def _windows_cpu_cache() -> dict:
    """Win32 GetLogicalProcessorInformation: no dependency on PowerShell or psutil."""
    if os.name != 'nt':
        return {}
    class CACHE_DESCRIPTOR(ctypes.Structure):
        _fields_ = [('Level', ctypes.c_ubyte), ('Associativity', ctypes.c_ubyte),
                    ('LineSize', ctypes.c_ushort), ('Size', ctypes.c_uint32),
                    ('Type', ctypes.c_int)]
    class CORE_FLAGS(ctypes.Structure):
        _fields_ = [('Flags', ctypes.c_ubyte)]
    class NUMA_NODE(ctypes.Structure):
        _fields_ = [('NodeNumber', ctypes.c_uint32)]
    class INFO(ctypes.Union):
        _fields_ = [('ProcessorCore', CORE_FLAGS), ('NumaNode', NUMA_NODE),
                    ('Cache', CACHE_DESCRIPTOR), ('Reserved', ctypes.c_uint64 * 2)]
    class SYSTEM_INFO(ctypes.Structure):
        _fields_ = [('ProcessorMask', ctypes.c_size_t), ('Relationship', ctypes.c_uint32),
                    ('Info', INFO)]
    size = ctypes.c_uint32(0)
    fn = ctypes.windll.kernel32.GetLogicalProcessorInformation
    fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    fn.restype = ctypes.c_int
    fn(None, ctypes.byref(size))
    if not size.value:
        return {}
    buf = ctypes.create_string_buffer(size.value)
    if not fn(buf, ctypes.byref(size)):
        return {}
    records = ctypes.cast(buf, ctypes.POINTER(SYSTEM_INFO))
    n = size.value // ctypes.sizeof(SYSTEM_INFO)
    result = {'physical_cores': 0}
    cache_sizes: dict[int, list[int]] = {1: [], 2: [], 3: []}
    for i in range(n):
        rec = records[i]
        if rec.Relationship == 0:  # RelationProcessorCore
            result['physical_cores'] += 1
        elif rec.Relationship == 2:  # RelationCache
            cache = rec.Info.Cache
            if cache.Level == 1 and cache.Type != 1:  # Exclude instruction-only
                cache_sizes[1].append(cache.Size)
            elif cache.Level in (2, 3):
                cache_sizes[cache.Level].append(cache.Size)
            if cache.LineSize:
                result['cache_line_bytes'] = cache.LineSize
    for level, key in [(1, 'l1_data_cache_bytes_per_core'),
                       (2, 'l2_cache_bytes_per_core_or_cluster'),
                       (3, 'l3_shared_cache_bytes_per_domain')]:
        if cache_sizes[level]:
            result[key] = max(cache_sizes[level])
    if not result['physical_cores']:
        result.pop('physical_cores', None)
    return result


def _windows_description() -> dict:
    if os.name != 'nt':
        return {}
    d = _windows_cpu_cache()
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r'HARDWARE\DESCRIPTION\System\CentralProcessor\0')
        d['model'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
        d['reported_frequency_mhz'] = int(winreg.QueryValueEx(key, '~MHz')[0])
        d['frequency_source'] = 'Windows registry ~MHz (current/reported, not guaranteed base)'
    except (OSError, ValueError):
        pass
    return d


def _mac_description() -> dict:
    def sysctl(key: str) -> str | None:
        try:
            return subprocess.check_output(['sysctl', '-n', key], text=True, timeout=3).strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
    def num(key: str) -> int | None:
        raw = sysctl(key)
        return int(raw) if raw and raw.isdecimal() else None
    return {k: v for k, v in {
        'model': sysctl('machdep.cpu.brand_string') or platform.processor(),
        'physical_cores': num('hw.physicalcpu'),
        'l1_data_cache_bytes_per_core': num('hw.l1dcachesize'),
        'l2_cache_bytes_per_core_or_cluster': num('hw.l2cachesize'),
        'l3_shared_cache_bytes_per_domain': num('hw.l3cachesize'),
        'cache_line_bytes': num('hw.cachelinesize'),
        'reported_frequency_mhz': (num('hw.cpufrequency') or 0) / 1_000_000 or None,
        'frequency_source': 'hw.cpufrequency (if published)'
    }.items() if v is not None}


def get_profile() -> dict:
    system = platform.system()
    observed = (_linux_info() if system == 'Linux' else
                _windows_description() if system == 'Windows' else
                _mac_description() if system == 'Darwin' else {})
    logical = os.cpu_count() or 1
    physical = observed.get('physical_cores')
    if physical is None:
        try:
            import psutil  # optional, only if installed
            physical = psutil.cpu_count(logical=False)
        except ImportError:
            pass
    profile = {
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'hostname': platform.node(),
        'os': system,
        'os_release': platform.release(),
        'os_version': platform.version(),
        'architecture': platform.machine(),
        'cpu_model': observed.get('model', platform.processor()),
        # Microarchitecture is not identical to ISA (x86_64/arm64). Do not guess.
        'microarchitecture': 'not reliably identified; verify from CPU model datasheet',
        'physical_cores': physical,
        'logical_threads': logical,
        'smt_detected': (logical > physical) if physical else None,
        'l1_data_cache_bytes_per_core': observed.get('l1_data_cache_bytes_per_core'),
        'l2_cache_bytes_per_core_or_cluster': observed.get('l2_cache_bytes_per_core_or_cluster'),
        'l3_shared_cache_bytes_per_domain': observed.get('l3_shared_cache_bytes_per_domain'),
        'cache_line_bytes': observed.get('cache_line_bytes'),
        'reported_frequency_mhz': observed.get('reported_frequency_mhz'),
        'frequency_source': observed.get('frequency_source'),
        'python_version': sys.version.split()[0],
        'python_implementation': platform.python_implementation(),
        'python_executable': sys.executable,
        'raw_observations': observed,
    }
    return profile


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--student-id', required=True)
    args = p.parse_args()
    out = ROOT / 'results'
    out.mkdir(exist_ok=True)
    profile = get_profile()
    salt = get_student_params(args.student_id)
    (out / 'host_profile.json').write_text(json.dumps(profile, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (out / 'salted_params.json').write_text(json.dumps(salt, indent=2) + '\n', encoding='utf-8')
    print(f'Host: {profile["cpu_model"]}, physical={profile["physical_cores"]}, logical={profile["logical_threads"]}')
    print(f'Salted dimensions: N={salt["N"]}, buffer={salt["buffer_elements"]}, seed={salt["seed"]}')
    print('Wrote results/host_profile.json and results/salted_params.json')

if __name__ == '__main__':
    main()
