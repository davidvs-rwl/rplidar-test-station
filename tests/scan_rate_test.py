"""
Scan Rate Test

Measures the RPLIDAR scan motor rotation frequency (Hz).

The RPLIDAR A1 should rotate at approximately 5.5 Hz (5.5 rotations per second).
This test collects multiple scans and calculates the average scan rate.

Pass criteria (from test_limits.yaml):
- Minimum: 5.0 Hz
- Maximum: 10.0 Hz
"""

import time
import logging
from typing import List

from tests.base_test import BaseTest

logger = logging.getLogger(__name__)


class ScanRateTest(BaseTest):
    """
    Test to verify RPLIDAR scan motor rotation frequency.
    
    Collects multiple complete scans and measures the time between them
    to calculate the scan rate in Hz.
    """
    
    test_name = "scan_rate_test"
    
    def setup(self) -> None:
        """Ensure motor is running and stable before measuring."""
        logger.info("Starting motor and waiting for stabilization...")
        self.driver.start_motor(pwm=self.config.motor_default_pwm)
        
        # Wait for motor to reach stable speed
        stabilization_time = 2.0
        time.sleep(stabilization_time)
        logger.info("Motor stabilized")
    
    def execute(self) -> None:
        """
        Measure the scan rate by timing complete rotations.
        
        Records:
        - scan_rate_hz: Average rotation frequency
        - scan_rate_min_hz: Minimum observed rate
        - scan_rate_max_hz: Maximum observed rate
        - scan_count: Number of scans collected
        """
        # Get test parameters from limits config
        samples_required = self.limits.get("samples_required", 10)
        min_hz = self.limits.get("min_hz", 5.0)
        max_hz = self.limits.get("max_hz", 10.0)
        
        logger.info(f"Collecting {samples_required} scans to measure rate...")
        
        # Collect scan timestamps
        scan_times: List[float] = []
        
        # Start scanning
        self.driver.start_scan()
        
        try:
            scan_count = 0
            for scan in self.driver.iter_scans(max_scans=samples_required + 1):
                scan_times.append(time.time())
                scan_count += 1
                logger.debug(f"Scan {scan_count}: {len(scan)} points")
                
                if scan_count > samples_required:
                    break
        finally:
            self.driver.stop_scan()
        
        # Calculate scan rates from time differences
        scan_rates: List[float] = []
        for i in range(1, len(scan_times)):
            delta = scan_times[i] - scan_times[i-1]
            if delta > 0:
                rate = 1.0 / delta  # Hz = 1 / seconds_per_scan
                scan_rates.append(rate)
        
        if not scan_rates:
            logger.error("No scan rate data collected")
            self.record_result(
                name="scan_rate_hz",
                value=None,
                unit="Hz",
                lower_limit=min_hz,
                upper_limit=max_hz
            )
            return
        
        # Calculate statistics
        avg_rate = sum(scan_rates) / len(scan_rates)
        min_rate = min(scan_rates)
        max_rate = max(scan_rates)
        
        logger.info(f"Scan rate: {avg_rate:.2f} Hz (min: {min_rate:.2f}, max: {max_rate:.2f})")
        
        # Record results
        self.record_result(
            name="scan_rate_hz",
            value=round(avg_rate, 2),
            unit="Hz",
            lower_limit=min_hz,
            upper_limit=max_hz
        )
        
        self.record_result(
            name="scan_rate_min_hz",
            value=round(min_rate, 2),
            unit="Hz"
        )
        
        self.record_result(
            name="scan_rate_max_hz",
            value=round(max_rate, 2),
            unit="Hz"
        )
        
        self.record_result(
            name="scan_count",
            value=len(scan_rates),
            unit="scans"
        )
    
    def teardown(self) -> None:
        """Stop the motor after test."""
        logger.info("Stopping motor...")
        self.driver.stop_motor()


# =============================================================================
# Test when running directly (without hardware)
# =============================================================================

if __name__ == "__main__":
    print("Scan Rate Test - Structure Test")
    print("-" * 50)
    
    # We can't run the full test without hardware,
    # but we can verify the class is set up correctly
    
    print(f"Test name: {ScanRateTest.test_name}")
    print(f"Inherits from BaseTest: {issubclass(ScanRateTest, BaseTest)}")
    
    # Check that required methods exist
    methods = ["setup", "execute", "teardown"]
    for method in methods:
        has_method = hasattr(ScanRateTest, method)
        print(f"Has {method}(): {has_method}")
    
    print("\n" + "=" * 50)
    print("✓ ScanRateTest class structure verified!")
    print("\nTo run with hardware:")
    print("""
    from tests.scan_rate_test import ScanRateTest
    
    test = ScanRateTest(serial_number="DUT001")
    report = test.run()
    
    print(f"Status: {report.status.value}")
    print(f"Passed: {report.passed}")
    for result in report.results:
        print(f"  {result.name}: {result.value} {result.unit}")
    """)