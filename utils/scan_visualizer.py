"""
Scan Visualizer

Generates a visual plot of RPLIDAR scan data showing:
- All scan points in X/Y coordinates
- Cardinal direction labels
- Distance rings
- Sensor position at origin

Output: PNG file saved to results/

Usage:
    python -m utils.scan_visualizer
"""

import time
import math
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from utils.config_loader import Config
from drivers.rplidar_driver import RPLidarDriver, ScanPoint

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def polar_to_cartesian(angle_deg: float, distance_mm: float) -> Tuple[float, float]:
    """
    Convert polar coordinates (angle, distance) to cartesian (x, y).
    
    RPLIDAR convention:
    - 0° = Forward (+X)
    - 90° = Left (+Y)
    - 180° = Backward (-X)
    - 270° = Right (-Y)
    
    Args:
        angle_deg: Angle in degrees
        distance_mm: Distance in millimeters
        
    Returns:
        Tuple of (x_mm, y_mm)
    """
    angle_rad = math.radians(angle_deg)
    x = distance_mm * math.cos(angle_rad)
    y = distance_mm * math.sin(angle_rad)
    return x, y


def collect_scan_data(num_scans: int = 5) -> List[ScanPoint]:
    """Collect scan data from RPLIDAR."""
    config = Config()
    
    print(f"Connecting to RPLIDAR on {config.rplidar_port}...")
    
    all_points: List[ScanPoint] = []
    
    with RPLidarDriver(
        port=config.rplidar_port,
        baudrate=config.rplidar_baudrate,
        timeout=config.rplidar_timeout
    ) as driver:
        
        driver.start_motor()
        time.sleep(2)
        print("Motor running, collecting scans...")
        
        driver.start_scan()
        
        try:
            for i, scan in enumerate(driver.iter_scans(max_scans=num_scans)):
                all_points.extend(scan)
                print(f"  Scan {i+1}/{num_scans}: {len(scan)} points")
        finally:
            driver.stop_scan()
            driver.stop_motor()
    
    print(f"Total points collected: {len(all_points)}")
    return all_points


def create_visualization(points: List[ScanPoint], output_path: Path) -> None:
    """
    Create a visualization of the scan data.
    
    Args:
        points: List of scan points
        output_path: Path to save the PNG file
    """
    # Import matplotlib here (not at top) so the rest of the module
    # can be imported even if matplotlib isn't installed
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    
    # Convert to cartesian coordinates (in meters for readability)
    x_coords = []
    y_coords = []
    qualities = []
    
    for p in points:
        x, y = polar_to_cartesian(p.angle, p.distance)
        x_coords.append(x / 1000)  # Convert to meters
        y_coords.append(y / 1000)
        qualities.append(p.quality)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # Plot scan points
    scatter = ax.scatter(
        x_coords, y_coords,
        c=qualities,
        cmap='viridis',
        s=2,
        alpha=0.7
    )
    
    # Add colorbar for quality
    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label('Signal Quality', fontsize=10)
    
    # Mark sensor position at origin
    ax.scatter([0], [0], c='red', s=200, marker='*', zorder=5, label='Sensor')
    ax.annotate('SENSOR', (0, 0), textcoords="offset points", 
                xytext=(10, 10), fontsize=10, color='red', fontweight='bold')
    
    # Add cardinal direction arrows and labels
    max_range = max(max(abs(x) for x in x_coords), max(abs(y) for y in y_coords)) if x_coords else 5
    arrow_len = max_range * 0.15
    
    directions = [
        (arrow_len, 0, 'Forward (+X)\n0°', 'right'),
        (0, arrow_len, 'Left (+Y)\n90°', 'center'),
        (-arrow_len, 0, 'Backward (-X)\n180°', 'left'),
        (0, -arrow_len, 'Right (-Y)\n270°', 'center'),
    ]
    
    for dx, dy, label, ha in directions:
        ax.annotate(
            '',
            xy=(dx, dy),
            xytext=(0, 0),
            arrowprops=dict(arrowstyle='->', color='red', lw=2)
        )
        ax.annotate(
            label,
            xy=(dx * 1.3, dy * 1.3),
            fontsize=9,
            ha=ha,
            va='center',
            color='darkred',
            fontweight='bold'
        )
    
    # Add distance rings
    ring_distances = [1, 2, 3, 4, 5, 6]  # meters
    for r in ring_distances:
        if r < max_range * 1.1:
            circle = plt.Circle((0, 0), r, fill=False, color='gray', 
                               linestyle='--', alpha=0.5, linewidth=0.5)
            ax.add_patch(circle)
            ax.annotate(f'{r}m', (r * 0.707, r * 0.707), fontsize=8, 
                       color='gray', alpha=0.7)
    
    # Set equal aspect ratio and grid
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='k', linewidth=0.5)
    ax.axvline(x=0, color='k', linewidth=0.5)
    
    # Labels and title
    ax.set_xlabel('X (meters) - Forward/Backward', fontsize=12)
    ax.set_ylabel('Y (meters) - Left/Right', fontsize=12)
    ax.set_title('RPLIDAR Room Scan\n(Sensor at Origin)', fontsize=14, fontweight='bold')
    
    # Set axis limits with padding
    padding = max_range * 0.15
    ax.set_xlim(-max_range - padding, max_range + padding)
    ax.set_ylim(-max_range - padding, max_range + padding)
    
    # Add measurement annotations
    # Find distances in cardinal directions
    measurements = []
    for name, angle_center in [("Forward", 0), ("Left", 90), ("Backward", 180), ("Right", 270)]:
        dir_points = [p for p in points if abs(p.angle - angle_center) < 10 or 
                      abs(p.angle - angle_center - 360) < 10 or
                      abs(p.angle - angle_center + 360) < 10]
        if dir_points:
            distances = [p.distance for p in dir_points]
            median_dist = sorted(distances)[len(distances)//2] / 1000
            measurements.append(f"{name}: {median_dist:.2f}m")
    
    # Add measurements text box
    textstr = "Wall Distances:\n" + "\n".join(measurements)
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=props, family='monospace')
    
    # Add room dimension estimates
    forward_pts = [p for p in points if abs(p.angle - 0) < 10]
    backward_pts = [p for p in points if abs(p.angle - 180) < 10]
    left_pts = [p for p in points if abs(p.angle - 90) < 10]
    right_pts = [p for p in points if abs(p.angle - 270) < 10]
    
    dim_text = "Room Dimensions:\n"
    if forward_pts and backward_pts:
        fwd = sorted([p.distance for p in forward_pts])[len(forward_pts)//2] / 1000
        bwd = sorted([p.distance for p in backward_pts])[len(backward_pts)//2] / 1000
        dim_text += f"X-axis: {fwd + bwd:.2f}m\n"
    if left_pts and right_pts:
        lft = sorted([p.distance for p in left_pts])[len(left_pts)//2] / 1000
        rgt = sorted([p.distance for p in right_pts])[len(right_pts)//2] / 1000
        dim_text += f"Y-axis: {lft + rgt:.2f}m"
    
    ax.text(0.98, 0.98, dim_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', horizontalalignment='right',
            bbox=props, family='monospace')
    
    # Save figure
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nVisualization saved to: {output_path}")
    
    plt.close()


def main():
    """Run the visualizer."""
    print("=" * 60)
    print("RPLIDAR SCAN VISUALIZER")
    print("=" * 60)
    
    # Collect data
    points = collect_scan_data(num_scans=5)
    
    if not points:
        print("No scan data collected!")
        return
    
    # Generate output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path("results") / f"room_scan_{timestamp}.png"
    
    # Create visualization
    print("\nGenerating visualization...")
    create_visualization(points, output_path)
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()