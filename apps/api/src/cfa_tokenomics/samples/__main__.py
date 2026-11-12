"""python -m cfa_tokenomics.samples OUT_DIR [--month YYYY-MM] [--seed N] [--identity]"""

import re
import sys

from .generate import write


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 2
    out = argv[0]
    month = argv[argv.index("--month") + 1] if "--month" in argv else "2026-10"
    seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else 7
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        print("month must look like 2026-10", file=sys.stderr)
        return 2
    for rel in write(out, month, seed, "--identity" in argv):
        print(rel)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
