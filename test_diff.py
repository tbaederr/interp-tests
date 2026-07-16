#!/usr/bin/env python3
"""
Test Diff Analyzer
Compares two test output files and generates an HTML report showing differences per test.
"""

import sys
import re
import json
import argparse
from typing import Dict, Set, Tuple, List
from pathlib import Path
from dataclasses import dataclass


@dataclass
class VerifyDiagnostics:
    """Holds diagnostic information for a -verify test."""
    expected_not_seen: List[str]  # Diagnostics expected but not seen
    seen_not_expected: List[str]  # Diagnostics seen but not expected


def parse_verify_diagnostics(lines: List[str]) -> VerifyDiagnostics:
    """
    Parse diagnostics from a -verify test failure.
    Returns VerifyDiagnostics with expected_not_seen and seen_not_expected lists.
    """
    expected_not_seen = []
    seen_not_expected = []

    in_expected_section = False
    in_seen_section = False

    for line in lines:
        line = line.strip()

        # Check for section headers FIRST (handle both old and new formats)
        # Old: "error: 'expected-error' diagnostics expected but not seen:"
        # New: "error: diagnostics with 'error' severity expected but not seen:"
        if "expected but not seen:" in line:
            in_expected_section = True
            in_seen_section = False
            continue
        elif "seen but not expected:" in line:
            in_expected_section = False
            in_seen_section = True
            continue
        elif (line.startswith("# | error:") and "diagnostics" not in line) or line.startswith("# `"):
            # End of diagnostic sections (but not section headers which also start with "# | error:")
            in_expected_section = False
            in_seen_section = False
            continue

        # Parse diagnostic lines (start with "# |   File")
        if line.startswith("# |   File "):
            # Extract file path, line number, and message
            # Format: # |   File <path> Line <num> [optional-parts]: <message>
            # Example: # |   File /path Line 231 'nointerpreter-error': message
            # Example: # |   File /path Line 304: message
            # Example: # |   File /path Line 214 (directive at /path:215) 'since-cxx11-error': message
            match = re.match(r'#\s+\|\s+File\s+(.+?)\s+Line\s+(\d+)(?:\s+\([^)]+\))?(?:\s+[^:]+)?:\s+(.+)', line)
            if match:
                filepath = match.group(1)
                line_num = match.group(2)
                message = match.group(3)
                diag_str = f"Line {line_num}: {message}"

                if in_expected_section:
                    expected_not_seen.append(diag_str)
                elif in_seen_section:
                    seen_not_expected.append(diag_str)

    return VerifyDiagnostics(expected_not_seen, seen_not_expected)


def parse_test_file(filepath: Path) -> Tuple[Dict[str, str], Set[str], Dict[str, VerifyDiagnostics]]:
    """
    Parse a test output file and extract test results.
    Returns:
        - dictionary mapping test names to their status (PASS/FAIL/UPASS for unexpectedly passed)
        - set of test names that use -verify
        - dictionary mapping -verify test names to their diagnostics
    """
    tests = {}
    verify_tests = set()
    verify_diagnostics = {}
    current_test = None
    current_test_lines = []
    in_test = False
    in_unexpectedly_passed = False

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            # Check for "Unexpectedly Passed Tests" section
            if 'Unexpectedly Passed Tests' in line:
                in_unexpectedly_passed = True
                in_test = False
                continue

            # End of unexpectedly passed section (blank line or testing time)
            if in_unexpectedly_passed and (line.strip() == '' or 'Testing Time:' in line):
                in_unexpectedly_passed = False
                continue

            # Parse unexpectedly passed test entries (format: "  Test :: Name")
            if in_unexpectedly_passed and line.strip():
                test_name = line.strip()
                tests[test_name] = 'UPASS'
                continue

            # Match lines like: FAIL: Clang :: AST/ast-dump-APValue-struct.cpp (68 of 24650)
            match = re.match(r'^(PASS|FAIL):\s+(.+?)\s+\(\d+\s+of\s+\d+\)', line)
            if match:
                # Process previous test if it was a verify test
                if current_test and current_test in verify_tests and current_test_lines:
                    diagnostics = parse_verify_diagnostics(current_test_lines)
                    if diagnostics.expected_not_seen or diagnostics.seen_not_expected:
                        verify_diagnostics[current_test] = diagnostics

                status = match.group(1)
                test_name = match.group(2).strip()
                tests[test_name] = status
                current_test = test_name
                current_test_lines = []
                in_test = True
                in_unexpectedly_passed = False
            elif in_test:
                current_test_lines.append(line)
                # Check for -verify in executed command lines
                if current_test and '# executed command:' in line:
                    if ' -verify' in line or ' -verify ' in line:
                        verify_tests.add(current_test)

        # Process last test if needed
        if current_test and current_test in verify_tests and current_test_lines:
            diagnostics = parse_verify_diagnostics(current_test_lines)
            if diagnostics.expected_not_seen or diagnostics.seen_not_expected:
                verify_diagnostics[current_test] = diagnostics

    return tests, verify_tests, verify_diagnostics


def generate_diagnostic_comparison(test_name: str,
                                   file1_diag: VerifyDiagnostics,
                                   file2_diag: VerifyDiagnostics,
                                   file1_name: str,
                                   file2_name: str) -> str:
    """Generate HTML for comparing diagnostics between two files, showing only changes."""

    # Convert to sets for comparison
    file1_expected = set(file1_diag.expected_not_seen)
    file2_expected = set(file2_diag.expected_not_seen)
    file1_seen = set(file1_diag.seen_not_expected)
    file2_seen = set(file2_diag.seen_not_expected)

    # Find differences
    expected_removed = file1_expected - file2_expected
    expected_added = file2_expected - file1_expected
    seen_removed = file1_seen - file2_seen
    seen_added = file2_seen - file1_seen

    # If no changes, don't show anything
    if not (expected_removed or expected_added or seen_removed or seen_added):
        return ""

    html = """
        <div class="diagnostic-comparison has-change">
            <div class="diagnostic-diff">
"""

    # Show removed diagnostics (expected but not seen)
    if expected_removed:
        html += """
                <div class="diagnostic-section">
                    <div class="diagnostic-header diagnostic-removed">− Expected but not seen (removed):</div>
                    <ul class="diagnostic-list">
"""
        for diag in sorted(expected_removed):
            html += f"""                        <li class="diff-removed">{diag}</li>
"""
        html += """                    </ul>
                </div>
"""

    # Show added diagnostics (expected but not seen)
    if expected_added:
        html += """
                <div class="diagnostic-section">
                    <div class="diagnostic-header diagnostic-added">+ Expected but not seen (added):</div>
                    <ul class="diagnostic-list">
"""
        for diag in sorted(expected_added):
            html += f"""                        <li class="diff-added">{diag}</li>
"""
        html += """                    </ul>
                </div>
"""

    # Show removed diagnostics (seen but not expected)
    if seen_removed:
        html += """
                <div class="diagnostic-section">
                    <div class="diagnostic-header diagnostic-removed">− Seen but not expected (removed):</div>
                    <ul class="diagnostic-list">
"""
        for diag in sorted(seen_removed):
            html += f"""                        <li class="diff-removed">{diag}</li>
"""
        html += """                    </ul>
                </div>
"""

    # Show added diagnostics (seen but not expected)
    if seen_added:
        html += """
                <div class="diagnostic-section">
                    <div class="diagnostic-header diagnostic-added">+ Seen but not expected (added):</div>
                    <ul class="diagnostic-list">
"""
        for diag in sorted(seen_added):
            html += f"""                        <li class="diff-added">{diag}</li>
"""
        html += """                    </ul>
                </div>
"""

    html += """
            </div>
        </div>
"""

    return html


def compare_tests(file1_tests: Dict[str, str], file2_tests: Dict[str, str]) -> Tuple[Dict, Dict, Dict, Set, Set]:
    """
    Compare test results from two files.
    Since the files only list failing tests:
    - Tests only in file1 (not in file2) were FIXED
    - Tests only in file2 (not in file1) are newly BROKEN
    - UPASS (unexpectedly passed) is treated similarly to PASS

    Returns:
        - fixed_tests: tests that were fixed (in file1, not in file2, or FAIL→PASS/UPASS)
        - broken_tests: tests that broke (not in file1, in file2, or PASS/UPASS→FAIL)
        - still_failing: tests that failed in both
        - only_in_file1: empty set (kept for compatibility)
        - only_in_file2: empty set (kept for compatibility)
    """
    all_tests = set(file1_tests.keys()) | set(file2_tests.keys())

    fixed_tests = {}
    broken_tests = {}
    still_failing = {}
    only_in_file1 = set()
    only_in_file2 = set()

    for test in all_tests:
        status1 = file1_tests.get(test)
        status2 = file2_tests.get(test)

        if status1 is None:
            # Test not in file1 but in file2 = newly broken (or newly unexpectedly passed)
            broken_tests[test] = (None, status2)
        elif status2 is None:
            # Test in file1 but not in file2 = fixed
            fixed_tests[test] = (status1, None)
        elif status1 == 'FAIL' and status2 in ('PASS', 'UPASS'):
            fixed_tests[test] = (status1, status2)
        elif status1 in ('PASS', 'UPASS') and status2 == 'FAIL':
            broken_tests[test] = (status1, status2)
        elif status1 == 'FAIL' and status2 == 'FAIL':
            still_failing[test] = (status1, status2)
        elif status1 in ('PASS', 'UPASS') and status2 in ('PASS', 'UPASS'):
            # Both passing or unexpectedly passing - track if status changed
            if status1 != status2:
                broken_tests[test] = (status1, status2)

    return fixed_tests, broken_tests, still_failing, only_in_file1, only_in_file2


def parse_ignore_list(filepath: Path) -> Dict[str, str]:
    """
    Parse an ignore list file.
    Format: test_name = reason for ignoring
    Lines starting with # are comments, empty lines are skipped.
    Returns a dictionary mapping test names to reasons.
    """
    ignore_list = {}

    if not filepath.exists():
        return ignore_list

    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse key = value format
            if '=' in line:
                parts = line.split('=', 1)
                test_name = parts[0].strip()
                reason = parts[1].strip() if len(parts) > 1 else "No reason provided"
                ignore_list[test_name] = reason
            else:
                print(f"Warning: Ignoring malformed line {line_num} in ignore list: {line}")

    return ignore_list


def find_dated_files(directory: Path) -> List[Path]:
    """Find all files matching YYYY-MM-DD.txt pattern in directory."""
    import re
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}\.txt$')

    files = []
    for file_path in directory.iterdir():
        if file_path.is_file() and date_pattern.match(file_path.name):
            files.append(file_path)

    # Sort by filename (which sorts chronologically due to YYYY-MM-DD format)
    return sorted(files)


def categorize_test_suite(test_name: str) -> str:
    """Categorize a test by its suite (libc++, Clang, etc.)."""
    # Handle libc++ tests - they use various config file names
    if test_name.startswith('llvm-libc++') or test_name.startswith('libc++ ::'):
        return 'libc++'
    elif test_name.startswith('Clang-Unit ::') or test_name.startswith('Clang ::'):
        return 'Clang'
    else:
        # Extract the suite name before the first '::'
        parts = test_name.split(' :: ', 1)
        if len(parts) > 1:
            # Clean up the suite name
            suite = parts[0].split(' ', 1)[0] if ' ' in parts[0] else parts[0]
            # Handle other libc++ variations
            if 'libc++' in suite.lower():
                return 'libc++'
            return suite
        return 'Other'


def generate_multi_file_html(all_pairs: List[Tuple[Path, Path, Dict, Dict, Dict, Set, Set, Dict, Dict, Set, Dict, Dict]],
                             display_pairs: List[Tuple[Path, Path, Dict, Dict, Dict, Set, Set, Dict, Dict, Set, Dict, Dict]],
                             total_pairs: int,
                             ignore_list: Dict[str, str] = None) -> str:
    """Generate HTML report for multiple file comparisons."""

    if ignore_list is None:
        ignore_list = {}

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Clang bytecode interpreter test results</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 10px;
            background-color: #f5f5f5;
            font-size: 13px;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 5px;
            margin: 10px 0;
            font-size: 1.3em;
        }
        .source-link {
            font-size: 0.6em;
            color: #999;
            font-weight: normal;
            margin-left: 10px;
            text-decoration: none;
        }
        .source-link:hover {
            color: #666;
            text-decoration: underline;
        }
        .chart-container {
            background: linear-gradient(to bottom, #ffffff 0%, #fafafa 100%);
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            margin-bottom: 20px;
            border: 1px solid rgba(0,0,0,0.05);
        }
        h2 {
            color: #555;
            margin-top: 15px;
            border-left: 3px solid #2196F3;
            padding-left: 8px;
            font-size: 1.1em;
        }
        .file-comparison {
            background-color: white;
            padding: 10px;
            border-radius: 3px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 15px;
        }
        .comparison-header {
            font-size: 1.1em;
            font-weight: bold;
            color: #2196F3;
            margin-bottom: 8px;
            padding-bottom: 6px;
            border-bottom: 1px solid #e0e0e0;
        }
        .test-count {
            font-size: 0.85em;
            color: #666;
            font-weight: normal;
            margin-left: 10px;
        }
        .test-section {
            margin-top: 8px;
        }
        .test-list {
            list-style-type: none;
            padding: 0;
            margin: 0;
        }
        .test-item {
            padding: 4px 0;
            margin: 2px 0;
            border-radius: 2px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
        }
        .test-item.fixed {
            background-color: #d4edda;
            border-left: 4px solid #28a745;
        }
        .test-item.broken {
            background-color: #ffffff;
            color: #721c24;
        }
        .test-item.still-failing {
            background-color: #ffffff;
        }
        .test-item.only-in-file1 {
            background-color: #e7f3ff;
            border-left: 4px solid #2196F3;
        }
        .test-item.only-in-file2 {
            background-color: #f3e7ff;
            border-left: 4px solid #9c27b0;
        }
        .status {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-weight: bold;
            font-size: 0.85em;
            margin-left: 10px;
        }
        .status.pass {
            background-color: #28a745;
            color: white;
        }
        .status.fail {
            background-color: #dc3545;
            color: white;
        }
        .arrow {
            margin: 0 5px;
            color: #666;
        }
        .file-info {
            color: #666;
            font-size: 0.9em;
            margin: 10px 0;
        }
        .empty-section {
            color: #999;
            font-style: italic;
            padding: 10px;
        }
        .verify-badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-weight: bold;
            font-size: 0.75em;
            margin-left: 8px;
            background-color: #6c757d;
            color: white;
        }
        .diagnostic-comparison {
            margin-top: 5px;
            padding: 6px;
            background-color: #f8f9fa;
            border-radius: 2px;
            font-size: 0.8em;
        }
        .diagnostic-diff {
            padding: 6px;
            background-color: white;
            border-radius: 2px;
            border: 1px solid #dee2e6;
        }
        .diagnostic-section {
            margin: 5px 0;
        }
        .diagnostic-header {
            font-weight: bold;
            margin-bottom: 3px;
            color: #495057;
            font-size: 0.9em;
        }
        .diagnostic-list {
            list-style: none;
            padding-left: 10px;
            margin: 3px 0;
        }
        .diagnostic-list li {
            padding: 2px 4px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            margin: 1px 0;
            border-radius: 2px;
        }
        .diagnostic-expected {
            color: #856404;
        }
        .diagnostic-seen {
            color: #004085;
        }
        .diagnostic-added {
            color: #155724;
        }
        .diagnostic-removed {
            color: #721c24;
        }
        .diff-added {
            background-color: #d4edda;
            border-left: 3px solid #28a745;
        }
        .diff-removed {
            background-color: #f8d7da;
            border-left: 3px solid #dc3545;
        }
        .no-change {
            color: #6c757d;
            font-style: italic;
        }
        .has-change {
            background-color: #fff3cd;
        }
        .test-header {
            cursor: pointer;
            user-select: none;
        }
        .test-header:hover {
            opacity: 0.8;
        }
        .collapse-indicator {
            display: inline-block;
            margin-right: 8px;
            font-size: 0.8em;
            transition: transform 0.2s;
        }
        .collapse-indicator.expanded {
            transform: rotate(90deg);
        }
        .test-no-expand {
            padding-left: 20px;
        }
        .diff-count {
            display: inline-block;
            padding: 1px 6px;
            border-radius: 2px;
            font-weight: bold;
            font-size: 0.8em;
            margin-left: 8px;
            font-family: monospace;
        }
        .diff-count.positive {
            background-color: #f8d7da;
            color: #721c24;
        }
        .diff-count.negative {
            background-color: #d4edda;
            color: #155724;
        }
        .diff-count.neutral {
            background-color: #e2e3e5;
            color: #383d41;
        }
        .diagnostic-content {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }
        .diagnostic-content.expanded {
            max-height: 2000px;
            transition: max-height 0.5s ease-in;
        }
    </style>
    <script>
        function toggleDiagnostics(element) {
            const content = element.nextElementSibling;
            const indicator = element.querySelector('.collapse-indicator');

            if (content.classList.contains('expanded')) {
                content.classList.remove('expanded');
                indicator.classList.remove('expanded');
            } else {
                content.classList.add('expanded');
                indicator.classList.add('expanded');
            }
        }
    </script>
</head>
<body>
    <h1>Clang bytecode interpreter test results <a href="https://github.com/tbaederr/interp-tests" class="source-link">source code</a></h1>
"""

    # Collect failure counts for the chart, categorized by suite
    # We need all the file2 counts in chronological order
    # Use a list to maintain order: [(date, {suite: count, ...}), ...]
    all_dates_data = []

    for (file1_path, file2_path, fixed_tests, broken_tests, still_failing,
         only_in_file1, only_in_file2, file1_tests, file2_tests, verify_tests,
         file1_diagnostics, file2_diagnostics) in all_pairs:

        # Count tests by suite for this file
        suite_breakdown = {}
        for test_name in file2_tests.keys():
            suite = categorize_test_suite(test_name)
            suite_breakdown[suite] = suite_breakdown.get(suite, 0) + 1

        all_dates_data.append((file2_path.name, suite_breakdown))

    # Reverse to get chronological order (oldest to newest)
    all_dates_data.reverse()

    # Generate Chart.js chart with stacked areas
    if all_dates_data:
        # Get all unique labels (dates) and all suites
        all_labels = [name.replace('.txt', '') for name, _ in all_dates_data]
        all_suites = set()
        for _, suite_breakdown in all_dates_data:
            all_suites.update(suite_breakdown.keys())

        # Define colors for different suites - modern, vibrant palette
        suite_colors = {
            'Clang': {'border': '#3b82f6', 'bg': 'rgba(59, 130, 246, 0.3)'},
            'libc++': {'border': '#f59e0b', 'bg': 'rgba(245, 158, 11, 0.3)'},
            'Other': {'border': '#8b5cf6', 'bg': 'rgba(139, 92, 246, 0.3)'}
        }

        # Build datasets for Chart.js - ensure all datasets have the same length
        datasets = []
        for suite in sorted(all_suites):
            color_info = suite_colors.get(suite, {'border': '#666', 'bg': 'rgba(102, 102, 102, 0.6)'})

            # Build data array with 0 for dates where this suite had no failures
            data = [suite_breakdown.get(suite, 0) for _, suite_breakdown in all_dates_data]

            datasets.append({
                'label': suite,
                'data': data,
                'borderColor': color_info['border'],
                'backgroundColor': color_info['bg'],
                'fill': 'origin',
                'tension': 0.4,
                'borderWidth': 2,
                'pointRadius': 0,
                'pointHoverRadius': 6,
                'pointHoverBackgroundColor': color_info['border'],
                'pointHoverBorderColor': '#fff',
                'pointHoverBorderWidth': 2
            })

        html += """
    <div class="chart-container">
        <canvas id="failureChart" style="max-height: 350px;"></canvas>
    </div>
    <script>
        const ctx = document.getElementById('failureChart').getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: """ + json.dumps(all_labels) + """,
                datasets: """ + json.dumps(datasets) + """
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: 3,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            boxWidth: 15,
                            padding: 15,
                            font: {
                                size: 12,
                                family: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
                            },
                            usePointStyle: true,
                            pointStyle: 'circle'
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        cornerRadius: 6,
                        titleFont: {
                            size: 13,
                            weight: 'bold'
                        },
                        bodyFont: {
                            size: 12
                        },
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + context.parsed.y + ' failures';
                            },
                            footer: function(items) {
                                let sum = 0;
                                items.forEach(item => sum += item.parsed.y);
                                return 'Total: ' + sum + ' failures';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        stacked: false,
                        beginAtZero: true,
                        ticks: {
                            precision: 0,
                            font: {
                                size: 11
                            },
                            color: '#6b7280'
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)',
                            drawBorder: false
                        },
                        border: {
                            display: false
                        }
                    },
                    x: {
                        ticks: {
                            font: {
                                size: 10
                            },
                            color: '#6b7280',
                            maxRotation: 45,
                            minRotation: 45
                        },
                        grid: {
                            display: false
                        },
                        border: {
                            display: false
                        }
                    }
                }
            }
        });
    </script>
"""

    # Collect all ignored tests across all display_pairs
    all_ignored_tests = set()

    # Generate content for each file pair (only display_pairs)
    for (file1_path, file2_path, fixed_tests, broken_tests, still_failing,
         only_in_file1, only_in_file2, file1_tests, file2_tests, verify_tests,
         file1_diagnostics, file2_diagnostics) in display_pairs:

        # Count tests with changed diagnostics
        changed_diagnostics_count = 0
        for test in still_failing.keys():
            if (test in verify_tests and
                test in file1_diagnostics and
                test in file2_diagnostics):
                file1_diag = file1_diagnostics[test]
                file2_diag = file2_diagnostics[test]
                identical = (set(file1_diag.expected_not_seen) == set(file2_diag.expected_not_seen) and
                           set(file1_diag.seen_not_expected) == set(file2_diag.seen_not_expected))
                if not identical:
                    changed_diagnostics_count += 1

        # Count total failing tests and unexpectedly passed tests in file2
        fail_count = sum(1 for status in file2_tests.values() if status == 'FAIL')
        upass_count = sum(1 for status in file2_tests.values() if status == 'UPASS')

        # Build the count display
        count_parts = []
        if fail_count:
            count_parts.append(f"{fail_count} failing")
        if upass_count:
            count_parts.append(f"{upass_count} unexpectedly passed")
        count_text = ", ".join(count_parts) if count_parts else "0 tests"

        # Always show the comparison header
        html += f"""
    <div class="file-comparison">
        <div class="comparison-header">
            {file2_path.name}
            <span class="test-count">({count_text})</span>
        </div>
"""

        # Show message if no changes
        if changed_diagnostics_count == 0 and not broken_tests:
            html += """
        <div class="empty-section">
            No new failures or diagnostic differences detected.
        </div>
"""

        # Collect all tests to display (broken tests + tests with changed diagnostics)
        tests_to_display = []

        # Add broken (new) tests
        for test in broken_tests.keys():
            if test in ignore_list:
                all_ignored_tests.add((test, ignore_list[test]))
                continue
            status2 = broken_tests[test][1]  # Get the current status
            tests_to_display.append((test, 'new', status2))

        # Add still failing tests with changed diagnostics
        if still_failing:
            for test in still_failing.keys():
                if test in ignore_list:
                    all_ignored_tests.add((test, ignore_list[test]))
                    continue
                if (test in verify_tests and
                    test in file1_diagnostics and
                    test in file2_diagnostics):
                    file1_diag = file1_diagnostics[test]
                    file2_diag = file2_diagnostics[test]
                    identical = (set(file1_diag.expected_not_seen) == set(file2_diag.expected_not_seen) and
                               set(file1_diag.seen_not_expected) == set(file2_diag.seen_not_expected))
                    if not identical:
                        tests_to_display.append((test, 'changed', (file1_diag, file2_diag)))

        # Sort all tests alphabetically by test name
        tests_to_display.sort(key=lambda x: x[0])

        if tests_to_display:
            html += """
        <div class="test-section">
            <ul class="test-list">
"""
            for test, test_type, diag_data in tests_to_display:
                if test_type == 'new':
                    # diag_data contains the status for new tests
                    status = diag_data

                    # Check if there are diagnostics to show
                    has_diagnostics = (test in file2_diagnostics and
                                     (file2_diagnostics[test].expected_not_seen or
                                      file2_diagnostics[test].seen_not_expected))

                    # Determine the badge text and style
                    if status == 'UPASS':
                        badge_text = 'UPASS'
                        badge_class = 'positive'
                    else:
                        badge_text = 'NEW'
                        badge_class = 'neutral'

                    # New failure - show with indicator
                    if has_diagnostics:
                        html += f"""                <li class="test-item still-failing">
                    <div class="test-header" onclick="toggleDiagnostics(this)">
                        <span class="collapse-indicator">▶</span>
                        {test}
                        <span class="diff-count {badge_class}">{badge_text}</span>
                    </div>
                    <div class="diagnostic-content">
"""
                    else:
                        html += f"""                <li class="test-item still-failing">
                    <div class="test-no-expand">
                        {test}
                        <span class="diff-count {badge_class}">{badge_text}</span>
                    </div>
"""

                    # Show the current diagnostics for new tests as "added"
                    if has_diagnostics:
                        file2_diag = file2_diagnostics[test]
                        if file2_diag.expected_not_seen or file2_diag.seen_not_expected:
                            html += """
        <div class="diagnostic-comparison has-change">
            <div class="diagnostic-diff">
"""
                            if file2_diag.expected_not_seen:
                                html += """
                <div class="diagnostic-section">
                    <div class="diagnostic-header diagnostic-added">+ Expected but not seen (added):</div>
                    <ul class="diagnostic-list">
"""
                                for diag in sorted(file2_diag.expected_not_seen):
                                    html += f"""                        <li class="diff-added">{diag}</li>
"""
                                html += """                    </ul>
                </div>
"""
                            if file2_diag.seen_not_expected:
                                html += """
                <div class="diagnostic-section">
                    <div class="diagnostic-header diagnostic-added">+ Seen but not expected (added):</div>
                    <ul class="diagnostic-list">
"""
                                for diag in sorted(file2_diag.seen_not_expected):
                                    html += f"""                        <li class="diff-added">{diag}</li>
"""
                                html += """                    </ul>
                </div>
"""
                            html += """
            </div>
        </div>
"""
                    if has_diagnostics:
                        html += """                    </div>
"""
                    html += """                </li>
"""
                else:  # test_type == 'changed'
                    # Calculate diagnostic diff count
                    file1_diag, file2_diag = diag_data

                    file1_expected = set(file1_diag.expected_not_seen)
                    file2_expected = set(file2_diag.expected_not_seen)
                    file1_seen = set(file1_diag.seen_not_expected)
                    file2_seen = set(file2_diag.seen_not_expected)

                    removed_count = len((file1_expected - file2_expected) | (file1_seen - file2_seen))
                    added_count = len((file2_expected - file1_expected) | (file2_seen - file1_seen))
                    net_change = added_count - removed_count

                    # Skip tests with zero net change
                    if net_change == 0:
                        continue

                    # Format the diff indicator
                    if net_change > 0:
                        diff_indicator = f'<span class="diff-count positive">+{net_change}</span>'
                    elif net_change < 0:
                        diff_indicator = f'<span class="diff-count negative">{net_change}</span>'
                    else:
                        diff_indicator = f'<span class="diff-count neutral">0</span>'

                    diff_html = generate_diagnostic_comparison(
                        test,
                        file1_diag,
                        file2_diag,
                        file1_path.name,
                        file2_path.name
                    )
                    if diff_html:
                        html += f"""                <li class="test-item still-failing">
                    <div class="test-header" onclick="toggleDiagnostics(this)">
                        <span class="collapse-indicator">▶</span>
                        {test}
                        {diff_indicator}
                    </div>
                    <div class="diagnostic-content">
"""
                        html += diff_html
                        html += """                    </div>
                </li>
"""
            html += """            </ul>
        </div>
"""

        html += """
    </div>
"""

    # Show ignored tests section once at the end if any tests were ignored
    if all_ignored_tests:
        html += f"""
    <div class="file-comparison" style="margin-top: 20px;">
        <div class="comparison-header" style="color: #6c757d;">
            Ignored Tests
            <span class="test-count">({len(all_ignored_tests)} test(s) filtered from output)</span>
        </div>
        <div class="test-section">
            <ul class="test-list">
"""
        for test, reason in sorted(all_ignored_tests):
            html += f"""                <li class="test-item" style="background-color: #f8f9fa; border-left: 4px solid #6c757d; color: #6c757d;">
                    {test}
                    <span style="font-style: italic; margin-left: 10px; font-size: 0.9em;">({reason})</span>
                </li>
"""
        html += """            </ul>
        </div>
    </div>
"""

    # Add a note about showing only the most recent results at the bottom
    if total_pairs > len(display_pairs):
        html += f"""
    <div class="file-info" style="background-color: #fff3cd; padding: 10px; border-radius: 3px; border-left: 4px solid #ffc107; margin-top: 15px;">
        <strong>Note:</strong> Showing the {len(display_pairs)} most recent test results out of {total_pairs} total comparisons.
        The chart above includes data from all {total_pairs} test runs.
    </div>
"""

    html += """
</body>
</html>
"""

    return html


def main():
    parser = argparse.ArgumentParser(
        description="Generates an HTML report comparing consecutive date-stamped test files (YYYY-MM-DD.txt)"
    )
    parser.add_argument(
        'directory',
        nargs='?',
        default='.',
        help='Directory containing test files (defaults to current directory)'
    )
    parser.add_argument(
        '-o', '--output',
        default='stats.html',
        help='Output HTML file (default: stats.html)'
    )
    parser.add_argument(
        '-i', '--ignore-list',
        default='ignore.txt',
        help='Ignore list file with tests to exclude (default: ignore.txt)'
    )

    args = parser.parse_args()
    directory = Path(args.directory)

    if not directory.exists():
        print(f"Error: Directory '{directory}' not found")
        sys.exit(1)

    if not directory.is_dir():
        print(f"Error: '{directory}' is not a directory")
        sys.exit(1)

    # Load ignore list
    ignore_list_path = Path(args.ignore_list)
    ignore_list = parse_ignore_list(ignore_list_path)
    if ignore_list:
        print(f"Loaded ignore list from {ignore_list_path}: {len(ignore_list)} test(s) to ignore")
    else:
        if ignore_list_path.exists():
            print(f"Ignore list file {ignore_list_path} is empty")
        else:
            print(f"No ignore list found at {ignore_list_path}")

    print(f"Scanning directory: {directory}")
    dated_files = find_dated_files(directory)

    if len(dated_files) < 2:
        print(f"Error: Found {len(dated_files)} dated file(s). Need at least 2 files to compare.")
        sys.exit(1)

    print(f"Found {len(dated_files)} dated files:")
    for f in dated_files:
        print(f"  - {f.name}")

    # Process consecutive pairs
    file_pairs = []
    for i in range(len(dated_files) - 1):
        file1_path = dated_files[i]
        file2_path = dated_files[i + 1]

        print(f"\nComparing {file1_path.name} → {file2_path.name}...")

        file1_tests, file1_verify, file1_diagnostics = parse_test_file(file1_path)
        file2_tests, file2_verify, file2_diagnostics = parse_test_file(file2_path)

        verify_tests = file1_verify | file2_verify

        fixed_tests, broken_tests, still_failing, only_in_file1, only_in_file2 = compare_tests(file1_tests, file2_tests)

        file_pairs.append((
            file1_path, file2_path, fixed_tests, broken_tests, still_failing,
            only_in_file1, only_in_file2, file1_tests, file2_tests, verify_tests,
            file1_diagnostics, file2_diagnostics
        ))

    print("\nGenerating HTML report...")
    # Reverse the order so most recent comparison is at the top
    all_pairs = list(reversed(file_pairs))

    # By default, show only the 5 most recent test results
    # (keeping all pairs for the chart data)
    display_pairs = all_pairs[:5]
    total_pairs = len(all_pairs)

    html = generate_multi_file_html(all_pairs, display_pairs, total_pairs, ignore_list)

    output_file = Path(args.output)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nReport generated: {output_file}")
    print(f"Compared {len(file_pairs)} consecutive file pair(s)")


if __name__ == '__main__':
    main()
