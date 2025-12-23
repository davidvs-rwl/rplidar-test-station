"""
Room Survey Utility

Takes scan measurements and reports distances in cardinal directions
to help determine room dimensions.

RPLIDAR Coordinate System:
- 0° = Forward (+X direction)
- 90° = Left (+Y direction)  
- 180° = Backward (-X direction)
- 270° = Right (-Y direction)

Usage:
    python -m utils.room_survey
"""

import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from utils.config_loader import Config
from drivers.rplidar_driver import RPLidarDriver, ScanPoint

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


@dataclass
class DirectionMeasurement:
    """Measurement in a specific direction."""
    direction: str
    angle_center: float
    distance_mm: float
    distance_m: float
    num_points: int


def get_points_in_range(
    scan: List[ScanPoint], 
    center_angle: float, 
    tolerance: float = 5.0
) -> List[ScanPoint]:
    """
    Get all points within a certain angle range.
    
    Args:
        scan: List of scan points
        center_angle: Center angle to look at (degrees)
        tolerance: +/- degrees to include
        
    Returns:
        List of points in that angular range
    """
    points = []
    for p in scan:
        # Calculate angular distance (handle wrap-around)
        diff = abs(p.angle - center_angle)
        if diff > 180:
            diff = 360 - diff
        
        if diff <= tolerance:
            points.append(p)
    
    return points


def measure_direction(
    scan: List[ScanPoint],
    direction_name: str,
    center_angle: float,
    tolerance: float = 10.0
) -> Optional[DirectionMeasurement]:
    """
    Measure distance in a specific direction.
    
    Args:
        scan: List of scan points
        direction_name: Name for this direction (e.g., "Forward")
        center_angle: Angle to measure (degrees)
        tolerance: Angular tolerance (degrees)
        
    Returns:
        DirectionMeasurement or None if no valid points
    """
    points = get_points_in_range(scan, center_angle, tolerance)
    
    if not points:
        return None
    
    # Use median distance to filter outliers
    distances = sorted([p.distance for p in points])
    median_distance = distances[len(distances) // 2]
    
    return DirectionMeasurement(
        direction=direction_name,
        angle_center=center_angle,
        distance_mm=round(median_distance, 1),
        distance_m=round(median_distance / 1000, 3),
        num_points=len(points)
    )


def run_survey(num_scans: int = 10) -> Dict[str, DirectionMeasurement]:
    """
    Run a room survey collecting measurements in all directions.
    
    Args:
        num_scans: Number of scans to average
        
    Returns:
        Dictionary of direction measurements
    """
    config = Config()
    
    print("=" * 60)
    print("ROOM SURVEY UTILITY")
    print("=" * 60)
    print(f"\nStation: {config.station_id}")
    print(f"Port: {config.rplidar_port}")
    print(f"\nCollecting {num_scans} scans...\n")
    
    # Cardinal directions to measure
    directions = [
        ("Forward (+X)", 0),
        ("Left (+Y)", 90),
        ("Backward (-X)", 180),
        ("Right (-Y)", 270),
    ]
    
    # Also measure diagonals for room corner detection
    diagonals = [
        ("Front-Left", 45),
        ("Back-Left", 135),
        ("Back-Right", 225),
        ("Front-Right", 315),
    ]
    
    all_scans: List[List[ScanPoint]] = []
    
    with RPLidarDriver(
        port=config.rplidar_port,
        baudrate=config.rplidar_baudrate,
        timeout=config.rplidar_timeout
    ) as driver:
        
        driver.start_motor()
        time.sleep(2)
        
        driver.start_scan()
        
        try:
            for i, scan in enumerate(driver.iter_scans(max_scans=num_scans)):
                all_scans.append(scan)
                print(f"  Scan {i+1}/{num_scans}: {len(scan)} points")
        finally:
            driver.stop_scan()
            driver.stop_motor()
    
    # Combine all scans
    combined_scan: List[ScanPoint] = []
    for scan in all_scans:
        combined_scan.extend(scan)
    
    print(f"\nTotal points collected: {len(combined_scan)}")
    
    # Measure cardinal directions
    print("\n" + "=" * 60)
    print("CARDINAL DIRECTIONS (Wall Distances)")
    print("=" * 60)
    
    results = {}
    
    for name, angle in directions:
        measurement = measure_direction(combined_scan, name, angle)
        if measurement:
            results[name] = measurement
            print(f"\n  {name} ({angle}°):")
            print(f"    Distance: {measurement.distance_m:.3f} m ({measurement.distance_mm:.0f} mm)")
            print(f"    Points: {measurement.num_points}")
        else:
            print(f"\n  {name} ({angle}°): No valid measurements")
    
    # Measure diagonals
    print("\n" + "=" * 60)
    print("DIAGONAL DIRECTIONS (Corners)")
    print("=" * 60)
    
    for name, angle in diagonals:
        measurement = measure_direction(combined_scan, name, angle)
        if measurement:
            results[name] = measurement
            print(f"\n  {name} ({angle}°):")
            print(f"    Distance: {measurement.distance_m:.3f} m ({measurement.distance_mm:.0f} mm)")
            print(f"    Points: {measurement.num_points}")
        else:
            print(f"\n  {name} ({angle}°): No valid measurements")
    
    # Calculate room dimensions
    print("\n" + "=" * 60)
    print("ESTIMATED ROOM DIMENSIONS")
    print("=" * 60)
    
    if "Forward (+X)" in results and "Backward (-X)" in results:
        x_dim = results["Forward (+X)"].distance_m + results["Backward (-X)"].distance_m
        print(f"\n  X-axis (Forward + Backward): {x_dim:.2f} m")
        print(f"    Forward:  {results['Forward (+X)'].distance_m:.3f} m")
        print(f"    Backward: {results['Backward (-X)'].distance_m:.3f} m")
    
    if "Left (+Y)" in results and "Right (-Y)" in results:
        y_dim = results["Left (+Y)"].distance_m + results["Right (-Y)"].distance_m
        print(f"\n  Y-axis (Left + Right): {y_dim:.2f} m")
        print(f"    Left:  {results['Left (+Y)'].distance_m:.3f} m")
        print(f"    Right: {results['Right (-Y)'].distance_m:.3f} m")
    
    print("\n" + "=" * 60)
    print("NOTES")
    print("=" * 60)
    print("""
  - Distances are from sensor to wall
  - Room dimensions = opposite wall distances added together
  - Furniture may cause shorter readings in some directions
  - Use these values to set expected dimensions in the room test
    """)
    
    return results


if __name__ == "__main__":
    run_survey()