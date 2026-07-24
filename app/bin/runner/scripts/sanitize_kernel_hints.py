#!/usr/bin/python3

"""Sanitise kernel-team hints against release-team hints.

Parse the existing hints files and accumulate release-team created blocks;
also detect block-all source.  Then run over the kernel-team/release hints
and reduce them to valid block/unblocks for approved packages which are not
also blocked by the release-team.  As part of this we "flatten" the
supplied blocks such that one appears per line which simplifies disabling
individual packages.
"""

import argparse
import re

BLOCK_RE = re.compile(r"^[ \t]*block[ \t]")
BLOCK_ALL_RE = re.compile(r"^[ \t]*block-all[ \t][ \t]*source")
HINTS_BLOCK_RE = re.compile(r"^block[ \t]")
HINTS_UNBLOCK_RE = re.compile(r"^unblock[ \t]")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sanitise kernel-team hints against release-team hints",
    )
    parser.add_argument("--hints", required=True)
    parser.add_argument("files", nargs="*")
    return parser.parse_args()


def main(hints, files):
    blocks = {}
    for path in files:
        # Ensure we do not consume our own output when considering blocks.
        if "/kernel-testing" in path:
            continue
        with open(path) as f:
            for line in f:
                if BLOCK_RE.search(line):
                    for token in line.split()[1:]:
                        blocks[token] = 1
                if BLOCK_ALL_RE.search(line):
                    blocks["ALL"] = 1

    for block in blocks:
        print("# RT BLOCKS " + block)

    with open(hints) as f:
        for line in f:
            line = line.rstrip("\n")
            # Blocks must only be linux packages and unversioned.
            if HINTS_BLOCK_RE.search(line):
                for token in line.split()[1:]:
                    if "/" in token:
                        print("# IGNORED(bad-form): block " + token)
                    elif token == "linux" or re.search(r"^linux-", token):
                        print("block " + token)
                    else:
                        print("# IGNORED(bad-package): block " + token)
            # Unblocks must only be linux packages, versioned, and not
            # in the manual blocks list.
            elif HINTS_UNBLOCK_RE.search(line):
                for token in line.split()[1:]:
                    first = token.split("/")[0]
                    if "ALL" in blocks or first in blocks:
                        print("# IGNORED(manually-blocked): unblock " + token)
                    elif re.search(r"^linux/", token) or re.search(r"^linux-[^/]*/", token):
                        print("unblock " + token)
                    else:
                        print("# IGNORED(bad-package/form): unblock " + token)
            # Comments and blank lines are ok.
            elif re.search(r"^#", line) or line == "":
                print(line)
            # Anything else is invalid.
            else:
                print("# IGNORED(invalid-directive): " + line)


if __name__ == "__main__":
    args = parse_args()
    main(args.hints, args.files)
