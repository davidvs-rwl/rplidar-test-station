"""
Angular Resolution Test

Measures the angular spacing between consecutive scan points.

The RPLIDAR A1 should have an angular resolution of ≤1 degree,
meaning consecutive measurements should be no more than 1 degree apart.

Pass criteria (from test_limits.yaml):
- Maximum resolution: 1.0 degree
- Minimum points per scan: 360
"""

import logging
from typing import List

from tests.base_test import BaseTest
from drivers.rplidar_driver import ScanPoint

logger = logging.getLogger(__name__)


class AngularResolutionTest(BaseTest):
    """
    Test to verify RPLIDAR angular resolution.
    
    Collects scan data and calculates the angular gaps between
    consecutive measurements to ensure the device meets resolution specs.
    """
    
    test_name = "angular_resolution_test"
    
    def setup(self) -> None:
        """Start motor and wait for stabilization."""
        logger.info("Starting motor...")
        self.driver.start_motor()
        
        import time
        time.sleep(2.0)
        logger.info("Motor stabilized")
    
    def execute(self) -> None:
        """
        Collect scans and analyze angular resolution.
        
        Records:
        - avg_resolution_deg: Average angular gap between points
        - max_resolution_deg: Maximum angular gap (worst case)
        - min_resolution_deg: Minimum angular gap
        - points_per_scan: Average number of points per 360° scan
        """
        # Get test parameters from limits
        max_resolution = self.limits.get("max_resolution_deg", 1.0)
        min_points = self.limits.get("min_points_per_scan", 360)
        num_scans = 5
        
        logger.info(f"Collecting {num_scans} scans for resolution analysis...")
        
        all_resolutions: List[float] = []
        points_per_scan: List[int] = []
        
        self.driver.start_scan()
        
        try:
            for i, scan in enumerate(self.driver.iter_scans(max_scans=num_scans)):
                if len(scan) < 2:
                    continue
                
                points_per_scan.append(len(scan))
                
                # Scan is already sorted by angle
                # Calculate gaps between consecutive points
                for j in range(1, len(scan)):
                    gap = scan[j].angle - scan[j-1].angle
                    
                    # Handle wrap-around (359° to 1°)
                    if gap < 0:
                        gap += 360.0
                    
                    # Ignore unreasonably large gaps (missing data regions)
                    if gap < 10.0:
                        all_resolutions.append(gap)
                
                logger.debug(f"Scan {i+1}: {len(scan)} points")
        finally:
            self.driver.stop_scan()
        
        if not all_resolutions:
            logger.error("No resolution data collected")
            self.record_result("avg_resolution_deg", None, upper_limit=max_resolution)
            return
        
        # Calculate statistics
        avg_resolution = sum(all_resolutions) / len(all_resolutions)
        max_res = max(all_resolutions)
        min_res = min(all_resolutions)
        avg_points = sum(points_per_scan) / len(points_per_scan) if points_per_scan else 0
        
        logger.info(f"Resolution: avg={avg_resolution:.3f}°, max={max_res:.3f}°, min={min_res:.3f}°")
        logger.info(f"Points per scan: {avg_points:.0f}")
        
        # Record results
        self.record_result(
            name="avg_resolution_deg",
            value=round(avg_resolution, 3),
            unit="deg",
            upper_limit=max_resolution
        )
        
        self.record_result(
            name="max_resolution_deg",
            value=round(max_res, 3),
            unit="deg",
            upper_limit=max_resolution
        )
        
        self.record_result(
            name="min_resolution_deg",
            value=round(min_res, 3),
            unit="deg"
        )
        
        self.record_result(
            name="points_per_scan",
            value=round(avg_points),
            unit="points",
            lower_limit=min_points
        )
    
    def teardown(self) -> None:
        """Stop motor after test."""
        logger.info("Stopping motor...")
        self.driver.stop_motor()


# =============================================================================
# Test when running directly
# =============================================================================

if __name__ == "__main__":
    print("Angular Resolution Test - Structure Test")
    print("-" * 50)
    
    print(f"Test name: {AngularResolutionTest.test_name}")
    print(f"Inherits from BaseTest: {issubclass(AngularResolutionTest, BaseTest)}")
    
    methods = ["setup", "execute", "teardown"]
    for method in methods:
        has_method = hasattr(AngularResolutionTest, method)
        print(f"Has {method}(): {has_method}")
    
    print("\n" + "=" * 50)
    print("✓ AngularResolutionTest class structure verified!")