"""
RPLIDAR A1 Driver

Hardware abstraction layer for communicating with the RPLIDAR A1 sensor.

This driver handles:
- Serial connection management
- Command protocol encoding/decoding
- Scan data collection and parsing

Usage:
    from drivers.rplidar_driver import RPLidarDriver
    
    with RPLidarDriver(port="/dev/ttyUSB0") as driver:
        info = driver.get_device_info()
        health = driver.get_health_status()
        
        for scan in driver.iter_scans(max_scans=10):
            print(f"Got {len(scan)} measurements")
"""

import serial
import logging
import struct
import time
from typing import Optional, Dict, Any, List, Tuple, Iterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# =============================================================================
# RPLIDAR Protocol Constants
# =============================================================================

SYNC_BYTE_1 = 0xA5
SYNC_BYTE_2 = 0x5A

CMD_STOP = 0x25
CMD_RESET = 0x40
CMD_SCAN = 0x20
CMD_EXPRESS_SCAN = 0x82
CMD_FORCE_SCAN = 0x21
CMD_GET_INFO = 0x50
CMD_GET_HEALTH = 0x52
CMD_GET_SAMPLERATE = 0x59
CMD_SET_PWM = 0xF0

DESCRIPTOR_SIZE = 7
INFO_SIZE = 20
HEALTH_SIZE = 3
SCAN_RESPONSE_SIZE = 5

RESPONSE_INFO = 0x04
RESPONSE_HEALTH = 0x06
RESPONSE_SCAN = 0x81

HEALTH_GOOD = 0
HEALTH_WARNING = 1
HEALTH_ERROR = 2

HEALTH_STATUS_NAMES = {
    HEALTH_GOOD: "Good",
    HEALTH_WARNING: "Warning",
    HEALTH_ERROR: "Error"
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ScanPoint:
    """
    A single measurement point from a scan.
    
    Attributes:
        angle: Angle in degrees (0-360)
        distance: Distance in millimeters (0 = invalid measurement)
        quality: Signal quality (0-63, higher is better)
        new_scan: True if this is the start of a new 360° scan
    """
    angle: float
    distance: float
    quality: int
    new_scan: bool


class RPLidarDriver:
    """
    Driver for RPLIDAR A1 sensor.
    
    Provides methods for connecting to the device, controlling the motor,
    and collecting scan data.
    """
    
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 2.0
    ):
        """
        Initialize the RPLIDAR driver.
        
        Args:
            port: Serial port (e.g., "/dev/ttyUSB0" or "COM3")
            baudrate: Communication speed (default 115200 for RPLIDAR A1)
            timeout: Read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
        self._serial: Optional[serial.Serial] = None
        self._scanning: bool = False
        
        logger.debug(f"RPLidarDriver initialized for port {port}")
    
    @property
    def is_connected(self) -> bool:
        """Check if the serial connection is open."""
        return self._serial is not None and self._serial.is_open
    
    @property
    def is_scanning(self) -> bool:
        """Check if a scan is currently in progress."""
        return self._scanning
    
    def connect(self) -> None:
        """Open serial connection to the RPLIDAR."""
        if self.is_connected:
            logger.warning("Already connected")
            return
        
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            logger.info(f"Connected to RPLIDAR on {self.port}")
        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            raise
    
    def disconnect(self) -> None:
        """Close the serial connection."""
        if self._serial is not None:
            try:
                if self._scanning:
                    self.stop_scan()
                self.stop_motor()
            except Exception:
                pass
            self._serial.close()
            self._serial = None
            logger.info("Disconnected from RPLIDAR")
    
    def __enter__(self) -> "RPLidarDriver":
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
    
    # =========================================================================
    # Low-Level Communication
    # =========================================================================
    
    def _send_command(self, command: int, payload: bytes = b"") -> None:
        """Send a command to the RPLIDAR."""
        if not self.is_connected:
            raise RuntimeError("Not connected to RPLIDAR")
        
        cmd_packet = bytes([SYNC_BYTE_1, command])
        
        if payload:
            cmd_packet += bytes([len(payload)]) + payload
            checksum = 0
            for byte in cmd_packet:
                checksum ^= byte
            cmd_packet += bytes([checksum])
        
        self._serial.write(cmd_packet)
        logger.debug(f"Sent command: {cmd_packet.hex()}")
    
    def _read_descriptor(self) -> Dict[str, int]:
        """Read and parse a response descriptor."""
        descriptor = self._serial.read(DESCRIPTOR_SIZE)
        
        if len(descriptor) != DESCRIPTOR_SIZE:
            raise RuntimeError(
                f"Incomplete descriptor: expected {DESCRIPTOR_SIZE} bytes, "
                f"got {len(descriptor)}"
            )
        
        if descriptor[0] != SYNC_BYTE_1 or descriptor[1] != SYNC_BYTE_2:
            raise RuntimeError(
                f"Invalid descriptor sync bytes: {descriptor[:2].hex()}"
            )
        
        size_and_mode = struct.unpack("<I", descriptor[2:6])[0]
        response_size = size_and_mode & 0x3FFFFFFF
        send_mode = size_and_mode >> 30
        data_type = descriptor[6]
        
        return {
            "size": response_size,
            "send_mode": send_mode,
            "data_type": data_type
        }
    
    # =========================================================================
    # Device Information Commands
    # =========================================================================
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get device information (model, firmware, hardware, serial number)."""
        self._send_command(CMD_GET_INFO)
        descriptor = self._read_descriptor()
        
        if descriptor["data_type"] != RESPONSE_INFO:
            raise RuntimeError(f"Unexpected response type: {descriptor['data_type']}")
        
        data = self._serial.read(INFO_SIZE)
        if len(data) != INFO_SIZE:
            raise RuntimeError(f"Incomplete device info: got {len(data)} bytes")
        
        return {
            "model": data[0],
            "firmware_minor": data[1],
            "firmware_major": data[2],
            "hardware": data[3],
            "serial_number": data[4:20].hex().upper()
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get device health status."""
        self._send_command(CMD_GET_HEALTH)
        descriptor = self._read_descriptor()
        
        if descriptor["data_type"] != RESPONSE_HEALTH:
            raise RuntimeError(f"Unexpected response type: {descriptor['data_type']}")
        
        data = self._serial.read(HEALTH_SIZE)
        if len(data) != HEALTH_SIZE:
            raise RuntimeError(f"Incomplete health data: got {len(data)} bytes")
        
        status = data[0]
        error_code = struct.unpack("<H", data[1:3])[0]
        
        return {
            "status": status,
            "status_name": HEALTH_STATUS_NAMES.get(status, "Unknown"),
            "error_code": error_code
        }
    
    # =========================================================================
    # Motor Control
    # =========================================================================
    
    def stop_motor(self) -> None:
        """Stop the scan motor by setting DTR low."""
        if self._serial is not None:
            self._serial.dtr = False
        logger.info("Motor stopped")
    
    def start_motor(self, pwm: int = 660) -> None:
        """
        Start the scan motor by setting DTR high.
        
        Args:
            pwm: Ignored for A1 (kept for API compatibility)
        """
        if self._serial is not None:
            self._serial.dtr = True
        logger.info("Motor started")
    
    def set_motor_pwm(self, pwm: int) -> None:
        """
        Set motor PWM - for A1, this just starts/stops motor.
        
        Args:
            pwm: PWM value (0 = stop, >0 = start)
        """
        if pwm == 0:
            self.stop_motor()
        else:
            self.start_motor()
    
    # =========================================================================
    # Scanning
    # =========================================================================
    
    def start_scan(self) -> None:
        """
        Start a standard scan.
        
        After calling this, use iter_measurements() or iter_scans() to
        retrieve data.
        """
        if self._scanning:
            raise RuntimeError("Scan already in progress")
        
        # Ensure motor is running
        self.start_motor()
        time.sleep(0.5)  # Wait for motor to stabilize
        
        # Send scan command
        self._send_command(CMD_SCAN)
        
        # Read and verify descriptor
        descriptor = self._read_descriptor()
        if descriptor["data_type"] != RESPONSE_SCAN:
            raise RuntimeError(f"Unexpected scan response type: {descriptor['data_type']}")
        
        self._scanning = True
        logger.info("Scan started")
    
    def stop_scan(self) -> None:
        """Stop the current scan."""
        self._send_command(CMD_STOP)
        time.sleep(0.1)
        self._scanning = False
        if self.is_connected:
            self._serial.reset_input_buffer()
        logger.info("Scan stopped")
    
    def _parse_scan_response(self, data: bytes) -> ScanPoint:
        """
        Parse a 5-byte scan response into a ScanPoint.
        
        Byte format:
        [0]: quality(6) | new_scan(1) | check(1)
        [1]: angle_low(7) | check(1)
        [2]: angle_high(8)
        [3]: distance_low(8)
        [4]: distance_high(8)
        """
        # Extract quality (upper 6 bits of byte 0)
        quality = data[0] >> 2
        
        # Extract new_scan flag (bit 0 of byte 0)
        new_scan = bool(data[0] & 0x01)
        
        # Extract angle (15 bits: 7 from byte 1, 8 from byte 2)
        # Stored in units of 1/64 degree
        angle_raw = ((data[1] >> 1) | (data[2] << 7))
        angle = angle_raw / 64.0
        
        # Extract distance (16 bits: bytes 3-4)
        # Stored in units of 1/4 mm
        distance_raw = data[3] | (data[4] << 8)
        distance = distance_raw / 4.0
        
        return ScanPoint(
            angle=angle,
            distance=distance,
            quality=quality,
            new_scan=new_scan
        )
    
    def iter_measurements(self, max_points: int = 0) -> Iterator[ScanPoint]:
        """
        Iterate over individual scan measurements.
        
        Args:
            max_points: Maximum points to yield (0 = unlimited)
            
        Yields:
            ScanPoint objects with angle, distance, quality, new_scan
        """
        if not self._scanning:
            self.start_scan()
        
        count = 0
        while max_points == 0 or count < max_points:
            data = self._serial.read(SCAN_RESPONSE_SIZE)
            
            if len(data) != SCAN_RESPONSE_SIZE:
                logger.warning(f"Incomplete scan data: got {len(data)} bytes")
                continue
            
            point = self._parse_scan_response(data)
            yield point
            count += 1
    
    def iter_scans(self, max_scans: int = 0) -> Iterator[List[ScanPoint]]:
        """
        Iterate over complete 360° scans.
        
        Each yielded list contains all points from one full rotation,
        sorted by angle.
        
        Args:
            max_scans: Maximum number of complete scans to yield (0 = unlimited)
            
        Yields:
            List of ScanPoint objects for each complete scan
        """
        if not self._scanning:
            self.start_scan()
        
        current_scan: List[ScanPoint] = []
        scan_count = 0
        
        for point in self.iter_measurements():
            if point.new_scan and current_scan:
                # Sort by angle and yield the completed scan
                current_scan.sort(key=lambda p: p.angle)
                yield current_scan
                scan_count += 1
                
                if max_scans > 0 and scan_count >= max_scans:
                    break
                
                current_scan = []
            
            # Only include valid measurements (distance > 0)
            if point.distance > 0:
                current_scan.append(point)
    
    def get_single_scan(self) -> List[ScanPoint]:
        """
        Collect and return a single complete 360° scan.
        
        Returns:
            List of ScanPoint objects sorted by angle
        """
        for scan in self.iter_scans(max_scans=1):
            return scan
        return []


# =============================================================================
# Test when running directly
# =============================================================================

if __name__ == "__main__":
    print("RPLIDAR Driver - Structure Test")
    print("-" * 50)
    
    driver = RPLidarDriver(port="/dev/ttyUSB0")
    
    print(f"Port: {driver.port}")
    print(f"Baudrate: {driver.baudrate}")
    print(f"Timeout: {driver.timeout}s")
    print(f"Is connected: {driver.is_connected}")
    print(f"Is scanning: {driver.is_scanning}")
    
    print("\n✓ Driver class instantiated successfully!")
    
    # Demonstrate ScanPoint dataclass
    print("\n" + "-" * 50)
    print("ScanPoint dataclass example:")
    example_point = ScanPoint(angle=45.5, distance=1500.0, quality=47, new_scan=False)
    print(f"  {example_point}")
    
    print("\n" + "=" * 50)
    print("To test with actual hardware on Jetson:")
    print("=" * 50)
    print("""
    from drivers.rplidar_driver import RPLidarDriver
    
    with RPLidarDriver(port="/dev/ttyUSB0") as driver:
        # Get device info
        info = driver.get_device_info()
        print(f"Model: {info['model']}")
        print(f"Serial: {info['serial_number']}")
        
        # Get health
        health = driver.get_health_status()
        print(f"Health: {health['status_name']}")
        
        # Collect 3 complete scans
        for i, scan in enumerate(driver.iter_scans(max_scans=3)):
            print(f"Scan {i+1}: {len(scan)} points")
            
            # Show first few points
            for point in scan[:5]:
                print(f"  Angle: {point.angle:.1f}°, "
                      f"Distance: {point.distance:.1f}mm, "
                      f"Quality: {point.quality}")
    """)