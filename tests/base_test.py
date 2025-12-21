"""
Base Test Infrastructure

Provides the foundation for all test sequences in the RPLIDAR test station.

All tests inherit from BaseTest, which handles:
- Hardware setup and teardown
- Result recording and pass/fail determination
- Timing and logging
- Standardized test execution flow

Usage:
    class ScanRateTest(BaseTest):
        test_name = "scan_rate_test"
        
        def execute(self):
            # Your test logic here
            scan_rate = measure_scan_rate()
            self.record_result("scan_rate_hz", scan_rate)
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from utils.config_loader import Config
from drivers.rplidar_driver import RPLidarDriver

logger = logging.getLogger(__name__)


class TestStatus(Enum):
    """Possible states for a test."""
    NOT_RUN = "not_run"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"  # Test crashed, didn't complete


@dataclass
class TestResult:
    """
    Container for a single measurement result.
    
    Attributes:
        name: Identifier for this measurement (e.g., "scan_rate_hz")
        value: The measured value
        unit: Unit of measurement (e.g., "Hz", "mm")
        lower_limit: Minimum acceptable value (None = no lower limit)
        upper_limit: Maximum acceptable value (None = no upper limit)
        passed: Whether this measurement is within limits
    """
    name: str
    value: Any
    unit: str = ""
    lower_limit: Optional[float] = None
    upper_limit: Optional[float] = None
    passed: Optional[bool] = None
    
    def evaluate(self) -> bool:
        """
        Evaluate if the value is within limits.
        
        Returns:
            True if within limits, False otherwise
        """
        if self.value is None:
            self.passed = False
            return False
        
        # Check lower limit
        if self.lower_limit is not None and self.value < self.lower_limit:
            self.passed = False
            return False
        
        # Check upper limit
        if self.upper_limit is not None and self.value > self.upper_limit:
            self.passed = False
            return False
        
        self.passed = True
        return True


@dataclass
class TestReport:
    """
    Complete report for a test run.
    
    Contains all measurements, timing, and overall pass/fail status.
    """
    test_name: str
    serial_number: str
    station_id: str
    status: TestStatus = TestStatus.NOT_RUN
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    results: List[TestResult] = field(default_factory=list)
    error_message: Optional[str] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate test duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def passed(self) -> bool:
        """Check if all results passed."""
        if self.status == TestStatus.ERROR:
            return False
        return all(r.passed for r in self.results if r.passed is not None)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for saving/logging."""
        return {
            "test_name": self.test_name,
            "serial_number": self.serial_number,
            "station_id": self.station_id,
            "status": self.status.value,
            "passed": self.passed,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "results": [
                {
                    "name": r.name,
                    "value": r.value,
                    "unit": r.unit,
                    "lower_limit": r.lower_limit,
                    "upper_limit": r.upper_limit,
                    "passed": r.passed
                }
                for r in self.results
            ]
        }


class BaseTest(ABC):
    """
    Abstract base class for all tests.
    
    Subclasses must:
    1. Set the `test_name` class attribute
    2. Implement the `execute()` method
    
    Optionally override:
    - setup(): Additional setup after hardware connection
    - teardown(): Additional cleanup before disconnection
    - analyze(): Custom pass/fail logic
    """
    
    # Subclasses must override this
    test_name: str = "base_test"
    
    def __init__(
        self,
        config: Optional[Config] = None,
        driver: Optional[RPLidarDriver] = None,
        serial_number: str = "UNKNOWN"
    ):
        """
        Initialize the test.
        
        Args:
            config: Configuration object (created if not provided)
            driver: RPLIDAR driver (created if not provided)
            serial_number: Device under test serial number
        """
        self.config = config or Config()
        self.serial_number = serial_number
        
        # Driver can be shared across tests or created per-test
        self._driver = driver
        self._owns_driver = driver is None  # Track if we created it
        
        # Test report
        self.report = TestReport(
            test_name=self.test_name,
            serial_number=serial_number,
            station_id=self.config.station_id
        )
        
        # Load test limits from config
        try:
            self.limits = self.config.get_test_limits(self.test_name)
        except KeyError:
            logger.warning(f"No limits defined for {self.test_name}")
            self.limits = {}
    
    @property
    def driver(self) -> RPLidarDriver:
        """Get the RPLIDAR driver, creating if necessary."""
        if self._driver is None:
            self._driver = RPLidarDriver(
                port=self.config.rplidar_port,
                baudrate=self.config.rplidar_baudrate,
                timeout=self.config.rplidar_timeout
            )
        return self._driver
    
    # =========================================================================
    # Methods to Override in Subclasses
    # =========================================================================
    
    def setup(self) -> None:
        """
        Additional setup after hardware connection.
        
        Override this to add test-specific initialization.
        Default implementation does nothing.
        """
        pass
    
    @abstractmethod
    def execute(self) -> None:
        """
        Execute the test - MUST be implemented by subclasses.
        
        Use self.record_result() to record measurements.
        """
        pass
    
    def teardown(self) -> None:
        """
        Additional cleanup before hardware disconnection.
        
        Override this to add test-specific cleanup.
        Default implementation does nothing.
        """
        pass
    
    def analyze(self) -> None:
        """
        Analyze results and determine pass/fail.
        
        Default implementation evaluates each result against its limits.
        Override for custom pass/fail logic.
        """
        for result in self.report.results:
            result.evaluate()
    
    # =========================================================================
    # Result Recording
    # =========================================================================
    
    def record_result(
        self,
        name: str,
        value: Any,
        unit: str = "",
        lower_limit: Optional[float] = None,
        upper_limit: Optional[float] = None
    ) -> TestResult:
        """
        Record a test measurement.
        
        Args:
            name: Identifier for this measurement
            value: The measured value
            unit: Unit of measurement
            lower_limit: Minimum acceptable value
            upper_limit: Maximum acceptable value
            
        Returns:
            The created TestResult object
        """
        result = TestResult(
            name=name,
            value=value,
            unit=unit,
            lower_limit=lower_limit,
            upper_limit=upper_limit
        )
        self.report.results.append(result)
        logger.info(f"Recorded: {name} = {value} {unit}")
        return result
    
    # =========================================================================
    # Test Execution
    # =========================================================================
    
    def run(self) -> TestReport:
        """
        Run the complete test sequence.
        
        Returns:
            TestReport with all results and pass/fail status
        """
        logger.info(f"Starting test: {self.test_name}")
        self.report.status = TestStatus.RUNNING
        self.report.start_time = datetime.now()
        
        try:
            # Connect to hardware
            if not self.driver.is_connected:
                self.driver.connect()
            
            # Run test phases
            self.setup()
            self.execute()
            self.analyze()
            
            # Determine final status
            self.report.status = TestStatus.PASSED if self.report.passed else TestStatus.FAILED
            
        except Exception as e:
            logger.error(f"Test error: {e}")
            self.report.status = TestStatus.ERROR
            self.report.error_message = str(e)
            raise
            
        finally:
            # Always run teardown and cleanup
            try:
                self.teardown()
            except Exception as e:
                logger.error(f"Teardown error: {e}")
            
            # Disconnect if we created the driver
            if self._owns_driver and self._driver is not None:
                try:
                    self._driver.disconnect()
                except Exception:
                    pass
            
            self.report.end_time = datetime.now()
        
        # Log summary
        status = "PASSED" if self.report.passed else "FAILED"
        duration = self.report.duration_seconds or 0
        logger.info(f"Test {self.test_name} {status} in {duration:.2f}s")
        
        return self.report


# =============================================================================
# Test when running directly
# =============================================================================

if __name__ == "__main__":
    print("Base Test Infrastructure - Structure Test")
    print("-" * 50)
    
    # Test the data classes
    print("\n1. TestResult example:")
    result = TestResult(
        name="scan_rate",
        value=5.5,
        unit="Hz",
        lower_limit=5.0,
        upper_limit=10.0
    )
    result.evaluate()
    print(f"   {result}")
    print(f"   Passed: {result.passed}")
    
    print("\n2. TestReport example:")
    report = TestReport(
        test_name="example_test",
        serial_number="ABC123",
        station_id="STATION_01"
    )
    report.results.append(result)
    report.status = TestStatus.PASSED
    print(f"   Test: {report.test_name}")
    print(f"   Overall passed: {report.passed}")
    
    print("\n3. Report as dictionary:")
    report_dict = report.to_dict()
    for key, value in report_dict.items():
        print(f"   {key}: {value}")
    
    print("\n" + "=" * 50)
    print("✓ Base test infrastructure ready!")
    print("\nNote: Creating actual tests requires hardware connection.")