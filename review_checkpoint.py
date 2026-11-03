"""Create/verify an optional external history checkpoint; no model or network access."""
import argparse
import json
import sqlite3
from webapp.checkpoint import create_checkpoint, verify_checkpoint, write_checkpoint, read_checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('create')
    create.add_argument('--data-dir', required=True)
    create.add_argument('--case', required=True)
    create.add_argument('--output', required=True)
    verify = commands.add_parser('verify')
    verify.add_argument('--data-dir', required=True)
    verify.add_argument('--checkpoint', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'create':
            receipt = create_checkpoint(args.data_dir, args.case)
            write_checkpoint(args.output, args.data_dir, receipt)
            print('Checkpoint written. Keep an independent reviewer-controlled copy; no legal approval.')
        else:
            print(json.dumps(verify_checkpoint(args.data_dir, read_checkpoint(args.checkpoint)), indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        # No SQL, document text or private filesystem paths in error output.
        print(json.dumps(dict(status='CHECKPOINT_FAILED', error_type=type(exc).__name__)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
