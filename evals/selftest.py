#!/usr/bin/env python3
"""Run adversarial, broad regression, and synthetic long-form stress layers."""
from __future__ import annotations

import sys
import unittest

import test_regressions
import test_research
import test_stress
import v3_acceptance


def main() -> int:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(
        [
            loader.loadTestsFromModule(v3_acceptance),
            loader.loadTestsFromModule(test_regressions),
            loader.loadTestsFromModule(test_stress),
            loader.loadTestsFromModule(test_research),
        ]
    )
    count = suite.countTestCases()
    print(
        f"Palimpsest v3.5 selftest: {count} tests across "
        "adversarial, regression, and synthetic long-form stress layers",
        file=sys.stderr,
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
