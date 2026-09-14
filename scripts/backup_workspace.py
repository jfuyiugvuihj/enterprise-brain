import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.common.backup import create_backup


def main():
    parser = argparse.ArgumentParser(description="Back up enterprise brain data.")
    parser.add_argument("--source", default=".")
    parser.add_argument("--output", default="backups/enterprise-brain.zip")
    args = parser.parse_args()
    manifest = create_backup(Path(args.source), Path(args.output))
    print(f"created={args.output} files={manifest['files']}")


if __name__ == "__main__":
    main()
