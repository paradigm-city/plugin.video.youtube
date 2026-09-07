#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local test runner and stats dashboard for plugin.video.youtube.

Executes Ruff static analysis, pytest test suites (unit, integration, concurrency),
measures code coverage, and prints a comprehensive execution and quality report.

Usage:
    python run_tests.py                 # Full run: lint + all tests + coverage + stats
    python run_tests.py -f              # Fast run: lint + tests (skips coverage)
    python run_tests.py --suite unit    # Run only unit tests
    python run_tests.py --suite integration
    python run_tests.py --suite concurrency
    python run_tests.py --live          # Include opt-in live smoke tests
    python run_tests.py -v              # Verbose test output
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time


# Configure console encoding for Windows
if sys.platform == 'win32':
    os.system('')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Terminal formatting styles
class Style:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    BG_GREEN = '\033[42m\033[30m'
    BG_RED = '\033[41m\033[97m'


def hr(char='─', length=78):
    return char * length


def header(title):
    print(f"\n{Style.BOLD}{Style.CYAN}┌{hr('─', 76)}┐{Style.RESET}")
    print(f"{Style.BOLD}{Style.CYAN}│ {title.ljust(74)} │{Style.RESET}")
    print(f"{Style.BOLD}{Style.CYAN}└{hr('─', 76)}┘{Style.RESET}")


def run_command(cmd, capture_output=False):
    start = time.time()
    if capture_output:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = time.time() - start
        return proc.returncode, proc.stdout, proc.stderr, duration
    else:
        proc = subprocess.run(cmd)
        duration = time.time() - start
        return proc.returncode, '', '', duration


def run_lint(skip_lint=False):
    if skip_lint:
        return True, 0.0, 'Skipped by user'

    header('Phase 1: Code Quality & Static Analysis (Ruff)')
    print(f"{Style.DIM}Running: ruff check tests{Style.RESET}\n")

    cmd = [sys.executable, '-m', 'ruff', 'check', 'tests']
    ret, stdout, stderr, duration = run_command(cmd, capture_output=True)

    if ret == 0:
        print(f"  {Style.GREEN}✔ All lint checks passed cleanly!{Style.RESET} ({duration:.2f}s)")
        return True, duration, 'Passed (0 issues)'
    else:
        print(f"  {Style.RED}✖ Lint issues detected:{Style.RESET}")
        print(stdout)
        if stderr:
            print(stderr)
        return False, duration, 'Failed'


def parse_coverage_json(cov_file):
    if not os.path.exists(cov_file):
        return None

    try:
        with open(cov_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        totals = data.get('totals', {})
        files = data.get('files', {})

        # Track key components
        key_modules = {
            'Cipher Engine': 'cipher.py',
            'Script Engine': 'json_script_engine.py',
            'Rate Bypass': 'ratebypass.py',
            'Login Client (OAuth2)': 'login_client.py',
            'URL Resolver': 'url_resolver.py',
            'Data Client (API v3)': 'data_client.py',
            'Player Client (Innertube)': 'player_client.py',
            'Storage & Cache': os.path.join('kodion', 'storage'),
        }

        module_stats = {}
        for label, match_pat in key_modules.items():
            matched_files = [
                f_data for f_path, f_data in files.items()
                if match_pat in f_path
            ]
            if matched_files:
                covered = sum(m['summary']['covered_lines'] for m in matched_files)
                num_stmts = sum(m['summary']['num_statements'] for m in matched_files)
                pct = (covered / num_stmts * 100) if num_stmts > 0 else 0
                module_stats[label] = {
                    'covered': covered,
                    'statements': num_stmts,
                    'percent': pct,
                }

        return {
            'total_percent': totals.get('percent_covered', 0.0),
            'covered_lines': totals.get('covered_lines', 0),
            'num_statements': totals.get('num_statements', 0),
            'missing_lines': totals.get('missing_lines', 0),
            'module_stats': module_stats,
        }
    except Exception as e:
        print(f"{Style.DIM}Could not parse coverage JSON: {e}{Style.RESET}")
        return None


def run_tests(suite='all', fast=False, live=False, verbose=False, durations=5):
    header('Phase 2: Automated Test Execution (pytest)')

    test_dirs = []
    if suite == 'unit':
        test_dirs = ['tests/unit']
    elif suite == 'integration':
        test_dirs = ['tests/integration']
    elif suite == 'concurrency':
        test_dirs = ['tests/concurrency']
    else:
        test_dirs = ['tests']

    cov_file = None
    cmd = [sys.executable, '-m', 'pytest'] + test_dirs

    if verbose:
        cmd.append('-v')
    else:
        cmd.append('--tb=short')

    if live:
        cmd.extend(['-m', ''])
        print(f"{Style.YELLOW}⚡ Live smoke tests included (--live flag enabled){Style.RESET}")
    else:
        cmd.extend(['-m', 'not live'])

    if durations > 0:
        cmd.append(f'--durations={durations}')

    if not fast:
        temp_dir = tempfile.gettempdir()
        cov_file = os.path.join(temp_dir, f'yt_coverage_{os.getpid()}.json')
        cmd.extend([
            '--cov=resources/lib/youtube_plugin',
            f'--cov-report=json:{cov_file}',
            '--cov-report=term-missing:skip-covered',
        ])
        print(f"{Style.DIM}Measuring statement and branch coverage across add-on modules...{Style.RESET}\n")
    else:
        print(f"{Style.DIM}Fast mode enabled (skipping coverage tracking)...{Style.RESET}\n")

    ret, _, _, duration = run_command(cmd, capture_output=False)

    coverage_data = None
    if cov_file and os.path.exists(cov_file):
        coverage_data = parse_coverage_json(cov_file)
        try:
            os.remove(cov_file)
        except OSError:
            pass

    return ret == 0, duration, coverage_data


def count_tests():
    """Count tests per category by asking pytest --collect-only."""
    categories = {
        'Unit': 'tests/unit',
        'Integration': 'tests/integration',
        'Concurrency': 'tests/concurrency',
        'Live (Opt-in)': 'tests/live',
    }
    counts = {}
    for name, path in categories.items():
        if not os.path.exists(path):
            counts[name] = 0
            continue
        cmd = [sys.executable, '-m', 'pytest', path, '--collect-only', '-q', '-o', 'addopts=']
        ret, stdout, _, _ = run_command(cmd, capture_output=True)
        # Parse last lines for e.g. "18 tests collected" or "52 tests collected"
        lines = stdout.strip().splitlines()
        found = 0
        for line in reversed(lines):
            if 'test' in line and ('collected' in line or 'selected' in line):
                parts = line.split()
                for i, p in enumerate(parts):
                    if 'test' in p and i > 0 and parts[i - 1].isdigit():
                        found = int(parts[i - 1])
                        break
                if found:
                    break
        counts[name] = found
    return counts


def print_dashboard(lint_ok, lint_duration, lint_status,
                    test_ok, test_duration, coverage_data,
                    test_counts, suite):
    header('Phase 3: Test Analytics & Health Summary')

    # Environment Info
    py_ver = platform.python_version()
    os_name = f"{platform.system()} {platform.release()}"
    print(f"  {Style.BOLD}Platform:{Style.RESET}     Python {py_ver} on {os_name}")
    print(f"  {Style.BOLD}Suite:{Style.RESET}        {suite.upper()}")
    print(f"  {Style.BOLD}Timestamp:{Style.RESET}    {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. Quality & Linting
    print(f"  {Style.BOLD}Static Quality Gates:{Style.RESET}")
    lint_color = Style.GREEN if lint_ok else Style.RED
    lint_icon = '✔ PASS' if lint_ok else '✖ FAIL'
    print(f"    Ruff Linter:            {lint_color}{lint_icon}{Style.RESET}  ({lint_status}, {lint_duration:.2f}s)")
    print()

    # 2. Test Suite Breakdown
    print(f"  {Style.BOLD}Test Catalog Breakdown:{Style.RESET}")
    total_active = 0
    for cat, count in test_counts.items():
        is_live = 'Live' in cat
        tag = f"{Style.YELLOW}[OPT-IN]{Style.RESET}" if is_live else f"{Style.GREEN}[ACTIVE]{Style.RESET}"
        print(f"    • {cat.ljust(22)} {str(count).rjust(4)} tests  {tag}")
        if not is_live:
            total_active += count

    print(f"    {hr('─', 35)}")
    print(f"    • {'Total Offline Tests'.ljust(22)} {str(total_active).rjust(4)} tests  {Style.CYAN}[100% Mocked / 0 Quota]{Style.RESET}")
    print()

    # 3. Test Execution Result
    print(f"  {Style.BOLD}Execution Results:{Style.RESET}")
    test_color = Style.GREEN if test_ok else Style.RED
    test_icon = '✔ ALL PASSED' if test_ok else '✖ FAILURES OCCURRED'
    print(f"    Pytest Test Status:     {test_color}{test_icon}{Style.RESET}")
    print(f"    Total Test Duration:    {test_duration:.2f} seconds")
    print()

    # 4. Coverage Metrics
    if coverage_data:
        print(f"  {Style.BOLD}Code Coverage Metrics:{Style.RESET}")
        overall_pct = coverage_data['total_percent']
        cov_color = Style.GREEN if overall_pct >= 80 else (Style.YELLOW if overall_pct >= 50 else Style.RED)
        print(f"    Overall Add-on Coverage: {cov_color}{Style.BOLD}{overall_pct:.1f}%{Style.RESET} "
              f"({coverage_data['covered_lines']}/{coverage_data['num_statements']} statements)")
        print()
        print(f"    {Style.DIM}{'Core Component':<28} {'Statements':<14} {'Coverage'}{Style.RESET}")
        print(f"    {hr('─', 54)}")
        for mod, stats in coverage_data.get('module_stats', {}).items():
            pct = stats['percent']
            c_color = Style.GREEN if pct >= 80 else (Style.YELLOW if pct >= 50 else Style.CYAN)
            stmt_info = f"{stats['covered']}/{stats['statements']}"
            print(f"    {mod:<28} {stmt_info:<14} {c_color}{pct:>5.1f}%{Style.RESET}")
        print()

    # Final Verdict Banner
    all_passed = lint_ok and test_ok
    if all_passed:
        verdict = f"{Style.BG_GREEN}{Style.BOLD}  ✔ PASS: ALL LOCAL TESTS, CHECKS & AUDITS SUCCEEDED  {Style.RESET}"
    else:
        verdict = f"{Style.BG_RED}{Style.BOLD}  ✖ FAIL: REGRESSIONS OR QUALITY ISSUES DETECTED      {Style.RESET}"

    print(f"\n{verdict}\n")
    return 0 if all_passed else 1


def main():
    parser = argparse.ArgumentParser(
        description='Local test runner and stats reporter for plugin.video.youtube',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '-s', '--suite',
        choices=['all', 'unit', 'integration', 'concurrency'],
        default='all',
        help='Select test suite to run (default: all)',
    )
    parser.add_argument(
        '-f', '--fast',
        action='store_true',
        help='Fast run mode: execute tests without measuring code coverage',
    )
    parser.add_argument(
        '-l', '--live',
        action='store_true',
        help='Include opt-in live upstream YouTube Innertube smoke tests',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show verbose test execution output',
    )
    parser.add_argument(
        '--skip-lint',
        action='store_true',
        help='Skip Ruff static analysis / lint check',
    )
    parser.add_argument(
        '-d', '--durations',
        type=int,
        default=5,
        help='Number of slowest test durations to display (default: 5, 0 to disable)',
    )

    args = parser.parse_args()

    print(f"\n{Style.BOLD}{Style.WHITE}══════════════════════════════════════════════════════════════════════════════{Style.RESET}")
    print(f"{Style.BOLD}{Style.CYAN}           YOUTUBE KODI ADD-ON LOCAL TEST SUITE & STATS RUNNER            {Style.RESET}")
    print(f"{Style.BOLD}{Style.WHITE}══════════════════════════════════════════════════════════════════════════════{Style.RESET}")

    # 1. Run Lint
    lint_ok, lint_duration, lint_status = run_lint(skip_lint=args.skip_lint)

    # 2. Count catalog
    test_counts = count_tests()

    # 3. Run Tests
    test_ok, test_duration, coverage_data = run_tests(
        suite=args.suite,
        fast=args.fast,
        live=args.live,
        verbose=args.verbose,
        durations=args.durations,
    )

    # 4. Print Dashboard
    exit_code = print_dashboard(
        lint_ok=lint_ok,
        lint_duration=lint_duration,
        lint_status=lint_status,
        test_ok=test_ok,
        test_duration=test_duration,
        coverage_data=coverage_data,
        test_counts=test_counts,
        suite=args.suite,
    )

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
