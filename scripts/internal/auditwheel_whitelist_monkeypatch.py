"""Patch auditwheel to skip actions on libraries specified in the whitelist.
Other arguments are forwarded to auditwheel."""

import argparse
import sys

from auditwheel.main import main
from auditwheel.policy import WheelPolicies


def exclude_libs(whitelist):
    # Do not include the following libraries when repairing wheels.
    for lib in whitelist.split(';'):
        for p in WheelPolicies().policies:
            p['lib_whitelist'].append(lib)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Driver script to build ITK Python module wheels.')
    parser.add_argument('command', nargs=1, default='', help='auditwheel command (e.g. repair).')
    parser.add_argument('wheel_file', nargs=1, default='', help='auditwheel wheel file.')
    parser.add_argument('--wheel-dir', '-w', nargs=1, default='', type=str, help='Directory to store delocated wheels.')
    parser.add_argument('--whitelist', nargs=1, default=None, type=str, help='Semicolon-delimited libraries to exclude from repaired wheel (e.g. libcuda.so)')
    args = parser.parse_args()

    if args.whitelist is not None:
        whitelist = ';'.join(args.whitelist)
        exclude_libs(whitelist)
        # Do not forward whitelist args to auditwheel
        sys.argv.remove('--whitelist')
        sys.argv.remove(whitelist)

    sys.exit(main())
