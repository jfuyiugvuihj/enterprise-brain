"""Explicit preparation tool; importing or running without consent never downloads."""
import argparse
import os


def main(argv=None):
    parser = argparse.ArgumentParser(description='Download a reranker from an authorized model mirror.')
    parser.add_argument('--allow-download', action='store_true', help='Explicitly permit this download')
    parser.add_argument('--endpoint', default=os.getenv('HF_ENDPOINT', ''), help='Authorized mirror endpoint')
    parser.add_argument('--model', default='BAAI/bge-reranker-base')
    args = parser.parse_args(argv)
    if not args.allow_download:
        parser.error('Download disabled. Supply --allow-download only on an authorized preparation machine.')
    if not args.endpoint.startswith(('https://', 'http://')):
        parser.error('Provide an authorized --endpoint or HF_ENDPOINT before downloading.')
    os.environ['HF_ENDPOINT'] = args.endpoint
    from sentence_transformers import CrossEncoder
    CrossEncoder(args.model)
    print('Model download complete.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
