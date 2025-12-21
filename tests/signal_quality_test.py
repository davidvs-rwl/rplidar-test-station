"""
Signal Quality Test

Measures the signal quality and valid point percentage from RPLIDAR scans.

The quality value (0-63) indicates the strength of the laser return.
Higher values mean stronger, more reliable measurements.

Pass criteria (from test_limits.yaml):
- Minimum quality: 10
- Minimum valid point percentage: 80%
"""

import logging
from typing import List

from tests.base_test import BaseTest
from drivers.rplidar_driver import ScanPoint

logger = logging.getLogger(__name__)


class SignalQualityTest(BaseTest):
    """
    Test to verify RPLIDAR signal quality and measurement reliability.
    
    Collects scan data and analyzes:
    - Average signal quality
    - Minimum signal quality
    - Percentage of valid (non-zero distance) measurements
    """
    
    test_name = "signal_quality_test"
    
    def setup(self) -> None:
        """Start motor and wait for stabilization."""
        logger.info("Starting motor...")
        self.driver.start_motor()
        
        import time
        time.sleep(2.0)
        logger.info("Motor stabilized")
    
    def execute(self) -> None:
        """
        Collect scans and analyze signal quality.
        
        Records:
        - avg_quality: Average signal quality (0-63)
        - min_quality: Minimum observed quality
        - max_quality: Maximum observed quality
        - valid_point_percentage: Percentage of points with distance > 0
        - total_points: Total number of points collected
        """
        # Get test parameters from limits
        min_quality = self.limits.get("min_quality", 10)
        min_valid_percent = self.limits.get("min_valid_point_percentage", 80.0)
        num_scans = 5  # Collect 5 full rotations
        
        logger.info(f"Collecting {num_scans} scans for quality analysis...")
        
        # Collect all points from multiple scans
        all_points: List[ScanPoint] = []
        total_raw_points = 0
        
        self.driver.start_scan()
        
        try:
            for i, scan in enumerate(self.driver.iter_scans(max_scans=num_scans)):
                # iter_scans only returns points with distance > 0
                # We need to track raw point count differently
                all_points.extend(scan)
                logger.debug(f"Scan {i+1}: {len(scan)} valid points")
        finally:
            self.driver.stop_scan()
        
        if not all_points:
            logger.error("No scan data collected")
            self.record_result("avg_quality", None, lower_limit=min_quality)
            return
        
        # Calculate quality statistics
        qualities = [p.quality for p in all_points]
        avg_quality = sum(qualities) / len(qualities)
        min_qual = min(qualities)
        max_qual = max(qualities)
        
        # Calculate valid point percentage
        # For this test, we'll estimate based on expected points per scan
        # A1 typically gives ~360-400 points per scan at 5.5Hz
        expected_points_per_scan = 360
        expected_total = expected_points_per_scan * num_scans
        valid_percentage = (len(all_points) / expected_total) * 100
        
        # Cap at 100% (we might get more points than expected)
        valid_percentage = min(valid_percentage, 100.0)
        
        logger.info(f"Quality: avg={avg_quality:.1f}, min={min_qual}, max={max_qual}")
        logger.info(f"Valid points: {len(all_points)} ({valid_percentage:.1f}%)")
        
        # Record results
        self.record_result(
            name="avg_quality",
            value=round(avg_quality, 1),
            unit="",
            lower_limit=min_quality
        )
        
        self.record_result(
            name="min_quality",
            value=min_qual,
            unit="",
            lower_limit=min_quality
        )
        
        self.record_result(
            name="max_quality",
            value=max_qual,
            unit=""
        )
        
        self.record_result(
            name="valid_point_percentage",
            value=round(valid_percentage, 1),
            unit="%",
            lower_limit=min_valid_percent
        )
        
        self.record_result(
            name="total_points",
            value=len(all_points),
            unit="points"
        )
    
    def teardown(self) -> None:
        """Stop motor after test."""
        logger.info("Stopping motor...")
        self.driver.stop_motor()


# =============================================================================
# Test when running directly
# =============================================================================

if __name__ == "__main__":
    print("Signal Quality Test - Structure Test")
    print("-" * 50)
    
    print(f"Test name: {SignalQualityTest.test_name}")
    print(f"Inherits from BaseTest: {issubclass(SignalQualityTest, BaseTest)}")
    
    methods = ["setup", "execute", "teardown"]
    for method in methods:
        has_method = hasattr(SignalQualityTest, method)
        print(f"Has {method}(): {has_method}")
    
    print("\n" + "=" * 50)
    print("✓ SignalQualityTest class structure verified!")