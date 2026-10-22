import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.common.backup import restore_backup


def main():
    parser = argparse.ArgumentParser(description="Restore an enterprise brain backup.")
    parser.add_argument("archive")
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    manifest = restore_backup(Path(args.archive), Path(args.destination))
    print(f"restored={manifest['files']} created_at={manifest['created_at']}")


if __name__ == "__main__":
    main()
