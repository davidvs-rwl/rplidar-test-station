"""
RPLIDAR Test Station - Main Entry Point

Command-line interface for running tests on RPLIDAR devices.

Usage:
    python main.py --serial-number DUT001
    python main.py --serial-number DUT001 --test scan_rate
    python main.py --list-tests
    python main.py --help
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Type

from utils.config_loader import Config
from drivers.rplidar_driver import RPLidarDriver
from tests.base_test import BaseTest, TestReport, TestStatus
from tests.scan_rate_test import ScanRateTest
from tests.signal_quality_test import SignalQualityTest


# =============================================================================
# Test Registry
# =============================================================================
# Add new tests here as they are created

AVAILABLE_TESTS: Dict[str, Type[BaseTest]] = {
    "scan_rate": ScanRateTest,
    "signal_quality": SignalQualityTest,
    # "range_accuracy": RangeAccuracyTest,  # Future
    # "angular_resolution": AngularResolutionTest,  # Future
}


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(verbose: bool = False, log_file: str = None) -> None:
    """Configure logging for the test station."""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Format with timestamp
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


# =============================================================================
# Result Saving
# =============================================================================

def save_results(report: TestReport, results_dir: Path) -> Path:
    """
    Save test results to a JSON file.
    
    Args:
        report: The test report to save
        results_dir: Directory to save results in
        
    Returns:
        Path to the saved file
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{report.serial_number}_{report.test_name}_{timestamp}.json"
    filepath = results_dir / filename
    
    # Save as JSON
    with open(filepath, "w") as f:
        json.dump(report.to_dict(), f, indent=2)
    
    return filepath


# =============================================================================
# Test Execution
# =============================================================================

def run_single_test(
    test_class: Type[BaseTest],
    serial_number: str,
    config: Config,
    driver: RPLidarDriver = None
) -> TestReport:
    """
    Run a single test.
    
    Args:
        test_class: The test class to instantiate and run
        serial_number: Device under test serial number
        config: Configuration object
        driver: Optional shared driver instance
        
    Returns:
        TestReport with results
    """
    test = test_class(
        config=config,
        driver=driver,
        serial_number=serial_number
    )
    return test.run()


def run_all_tests(
    serial_number: str,
    config: Config
) -> Dict[str, TestReport]:
    """
    Run all available tests on a device.
    
    Args:
        serial_number: Device under test serial number
        config: Configuration object
        
    Returns:
        Dictionary mapping test names to their reports
    """
    reports = {}
    
    # Create shared driver for all tests
    driver = RPLidarDriver(
        port=config.rplidar_port,
        baudrate=config.rplidar_baudrate,
        timeout=config.rplidar_timeout
    )
    
    try:
        driver.connect()
        
        for test_name, test_class in AVAILABLE_TESTS.items():
            print(f"\n{'='*60}")
            print(f"Running: {test_name}")
            print('='*60)
            
            try:
                report = run_single_test(
                    test_class=test_class,
                    serial_number=serial_number,
                    config=config,
                    driver=driver
                )
                reports[test_name] = report
                
                status = "✓ PASSED" if report.passed else "✗ FAILED"
                print(f"Result: {status}")
                
            except Exception as e:
                print(f"✗ ERROR: {e}")
                
    finally:
        driver.disconnect()
    
    return reports


# =============================================================================
# Command Line Interface
# =============================================================================

def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="RPLIDAR Test Station",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --serial-number DUT001
  python main.py --serial-number DUT001 --test scan_rate
  python main.py --list-tests
  python main.py --serial-number DUT001 --verbose
        """
    )
    
    parser.add_argument(
        "--serial-number", "-s",
        type=str,
        help="Serial number of device under test"
    )
    
    parser.add_argument(
        "--test", "-t",
        type=str,
        choices=list(AVAILABLE_TESTS.keys()),
        help="Specific test to run (default: run all tests)"
    )
    
    parser.add_argument(
        "--list-tests", "-l",
        action="store_true",
        help="List available tests and exit"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) logging"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config/station_config.yaml",
        help="Path to station config file"
    )
    
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to file"
    )
    
    return parser


def print_summary(reports: Dict[str, TestReport]) -> None:
    """Print a summary of all test results."""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    total = len(reports)
    passed = sum(1 for r in reports.values() if r.passed)
    failed = total - passed
    
    for test_name, report in reports.items():
        status = "✓ PASS" if report.passed else "✗ FAIL"
        duration = f"{report.duration_seconds:.2f}s" if report.duration_seconds else "N/A"
        print(f"  {test_name:30s} {status:10s} ({duration})")
    
    print("-"*60)
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
    print("="*60)


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # List tests and exit
    if args.list_tests:
        print("Available tests:")
        for name in AVAILABLE_TESTS:
            print(f"  - {name}")
        return 0
    
    # Validate required arguments
    if not args.serial_number:
        parser.error("--serial-number is required (use --list-tests to see available tests)")
    
    # Setup logging
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)
    
    # Load configuration
    try:
        config = Config(station_config_path=args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return 1
    
    print(f"\nRPLIDAR Test Station")
    print(f"Station ID: {config.station_id}")
    print(f"Serial Number: {args.serial_number}")
    print(f"Port: {config.rplidar_port}")
    
    # Run tests
    try:
        if args.test:
            # Run single test
            test_class = AVAILABLE_TESTS[args.test]
            print(f"\n{'='*60}")
            print(f"Running: {args.test}")
            print('='*60)
            
            report = run_single_test(
                test_class=test_class,
                serial_number=args.serial_number,
                config=config
            )
            reports = {args.test: report}
        else:
            # Run all tests
            reports = run_all_tests(
                serial_number=args.serial_number,
                config=config
            )
        
        # Print summary
        print_summary(reports)
        
        # Save results
        if not args.no_save:
            for test_name, report in reports.items():
                filepath = save_results(report, config.results_directory)
                logger.info(f"Results saved: {filepath}")
        
        # Return exit code based on pass/fail
        all_passed = all(r.passed for r in reports.values())
        return 0 if all_passed else 1
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Test failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())