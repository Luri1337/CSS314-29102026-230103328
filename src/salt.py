import hashlib, os

def get_student_params(student_id: str):
    h = int(hashlib.sha256(student_id.encode('utf-8')).hexdigest()[:8], 16)
    # Salted matrix dimension N between 1024 and 1536 (multiple of 64)
    N = 1024 + ((h % 9) * 64)
    # Salted stride benchmark buffer size: 2^24 elements (~134 MB double-precision)
    buffer_elements = 16_777_216
    # Seed for deterministic random number generation
    seed = h % 100_007
    return {"student_id": student_id, "N": N, "buffer_elements": buffer_elements, "seed": seed}


import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_params() -> dict:
    path = ROOT / 'results' / 'salted_params.json'
    if not path.exists():
        raise FileNotFoundError(f'Missing {path}; first run profile_env.py --student-id YOUR_ID')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data != get_student_params(data['student_id']):
        raise ValueError('Salted parameters do not match SHA-256 formula.')
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--student-id', required=True, help='Your actual student ID, as a digit string')
    args = parser.parse_args()
    p = get_student_params(args.student_id)
    (ROOT / 'results').mkdir(exist_ok=True)
    (ROOT / 'results' / 'salted_params.json').write_text(json.dumps(p, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(p, indent=2))

if __name__ == '__main__':
    main()
