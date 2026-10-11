"""Read-only dataset check using an explicitly authorized API session."""
import argparse
import os
import sys
import requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-id', required=True)
    args = parser.parse_args()
    token = os.environ.get('AVENQO_API_ACCESS_TOKEN', '').strip()
    root = os.environ.get('AVENQO_API_BASE_URL', '').rstrip('/')
    if not token or not root.startswith('https://'):
        print('Explicit HTTPS API endpoint and authorized access token are required.', file=sys.stderr)
        return 2
    with requests.Session() as client:
        client.headers['Authorization'] = 'Bearer ' + token
        for suffix in ('', '/export/csv', '/cleaning'):
            try:
                response = client.get(root + '/datasets/' + args.dataset_id + suffix, timeout=30)
            except requests.RequestException:
                print('Dataset verification connection failed.', file=sys.stderr)
                return 1
            print(f'Dataset check HTTP {response.status_code}')
            if response.status_code != 200:
                return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
