"""
Configuration Loader Module

This module handles loading and validating configuration files for the test station.

Usage:
    from utils.config_loader import Config
    
    config = Config()
    port = config.rplidar_port
    limits = config.get_test_limits("scan_rate_test")
"""

from pathlib import Path
from typing import Any, Dict
import logging
import yaml

# Set up module logger
logger = logging.getLogger(__name__)


def load_yaml(filepath: Path) -> Dict[str, Any]:
    """
    Load a YAML file and return its contents as a dictionary.
    
    Args:
        filepath: Path to the YAML file
        
    Returns:
        Dictionary containing the YAML file contents
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the file contains invalid YAML
    """
    filepath = Path(filepath)
    
    if not filepath.exists():
        raise FileNotFoundError(f"Configuration file not found: {filepath}")
    
    with open(filepath, 'r') as f:
        try:
            data = yaml.safe_load(f)
            logger.debug(f"Loaded configuration from {filepath}")
            return data if data is not None else {}
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {filepath}: {e}")
            raise


def get_nested(data: Dict, *keys, default: Any = None) -> Any:
    """
    Safely get a nested value from a dictionary.
    
    Args:
        data: The dictionary to search
        *keys: Sequence of keys to traverse
        default: Value to return if any key is missing
        
    Returns:
        The value at the nested location, or default if not found
        
    Example:
        >>> config = {"station": {"rplidar": {"port": "COM3"}}}
        >>> get_nested(config, "station", "rplidar", "port")
        'COM3'
        >>> get_nested(config, "station", "missing", "key", default="N/A")
        'N/A'
    """
    result = data
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return default
    return result


class Config:
    """
    Configuration manager for the RPLIDAR test station.
    
    Loads station configuration and test limits from YAML files,
    providing convenient access to settings with validation.
    """
    
    def __init__(
        self,
        station_config_path: str = "config/station_config.yaml",
        test_limits_path: str = "config/test_limits.yaml"
    ):
        """
        Initialize the configuration manager.
        
        Args:
            station_config_path: Path to station configuration file
            test_limits_path: Path to test limits file
        """
        self._station_config: Dict[str, Any] = {}
        self._test_limits: Dict[str, Any] = {}
        
        # Load main configuration files
        self._station_config = load_yaml(Path(station_config_path))
        self._test_limits = load_yaml(Path(test_limits_path))
        
        # Load local overrides if they exist
        local_config_path = Path(station_config_path).parent / "local_station_config.yaml"
        if local_config_path.exists():
            local_config = load_yaml(local_config_path)
            self._merge_config(local_config)
            logger.info(f"Loaded local overrides from {local_config_path}")
        
        # Validate required fields
        self._validate_station_config()
        
        logger.info(f"Configuration loaded for station: {self.station_id}")
    
    def _merge_config(self, override_config: Dict[str, Any]) -> None:
        """Merge override configuration into station config (deep merge)."""
        def deep_merge(base: Dict, override: Dict) -> Dict:
            for key, value in override.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
            return base
        
        deep_merge(self._station_config, override_config)
    
    def _validate_station_config(self) -> None:
        """Validate that required configuration fields are present."""
        required_fields = [
            ("station", "id"),
            ("rplidar", "port"),
            ("rplidar", "baudrate"),
        ]
        
        missing = []
        for keys in required_fields:
            if get_nested(self._station_config, *keys) is None:
                missing.append(".".join(keys))
        
        if missing:
            raise ValueError(f"Missing required configuration fields: {', '.join(missing)}")
    
    # =========================================================================
    # Properties for convenient access to configuration values
    # =========================================================================
    
    @property
    def station_id(self) -> str:
        """Get the station identifier."""
        return get_nested(self._station_config, "station", "id", default="UNKNOWN")
    
    @property
    def rplidar_port(self) -> str:
        """Get the RPLIDAR serial port."""
        return get_nested(self._station_config, "rplidar", "port")
    
    @property
    def rplidar_baudrate(self) -> int:
        """Get the RPLIDAR baudrate."""
        return get_nested(self._station_config, "rplidar", "baudrate", default=115200)
    
    @property
    def rplidar_timeout(self) -> float:
        """Get the RPLIDAR communication timeout in seconds."""
        return get_nested(self._station_config, "rplidar", "timeout_sec", default=2.0)
    
    @property
    def motor_default_pwm(self) -> int:
        """Get the default motor PWM value."""
        return get_nested(self._station_config, "motor", "default_pwm", default=660)
    
    @property
    def results_directory(self) -> Path:
        """Get the results output directory as a Path object."""
        dir_name = get_nested(self._station_config, "data_output", "results_dir", default="results")
        return Path(dir_name)
    
    @property
    def log_level(self) -> str:
        """Get the logging level."""
        return get_nested(self._station_config, "logging", "level", default="INFO")
    
    # =========================================================================
    # Methods for accessing test limits
    # =========================================================================
    
    def get_test_limits(self, test_name: str) -> Dict[str, Any]:
        """
        Get limits for a specific test.
        
        Args:
            test_name: Name of the test (e.g., "scan_rate_test")
            
        Returns:
            Dictionary of limit values for the test
            
        Raises:
            KeyError: If the test name is not found
        """
        if test_name not in self._test_limits:
            raise KeyError(f"No limits defined for test: {test_name}")
        return self._test_limits[test_name]
    
    def get_accuracy_tolerance(self, distance_mm: float) -> Dict[str, Any]:
        """
        Get the accuracy tolerance for a given distance.
        
        Args:
            distance_mm: Distance in millimeters
            
        Returns:
            Dictionary with 'tolerance_mm' and/or 'tolerance_percent'
            
        Raises:
            ValueError: If distance is outside defined bands
        """
        accuracy_config = self.get_test_limits("range_accuracy_test")
        bands = accuracy_config.get("accuracy_bands", [])
        
        for band in bands:
            range_min, range_max = band["range"]
            if range_min <= distance_mm <= range_max:
                return {
                    "tolerance_mm": band.get("tolerance_mm"),
                    "tolerance_percent": band.get("tolerance_percent")
                }
        
        raise ValueError(
            f"Distance {distance_mm}mm is outside defined accuracy bands. "
            f"Valid range: {bands[0]['range'][0]}mm to {bands[-1]['range'][1]}mm"
        )


# =============================================================================
# Quick test when running this file directly
# =============================================================================

if __name__ == "__main__":
    print("Testing configuration loader...")
    print("-" * 50)
    
    try:
        config = Config()
        
        print(f"Station ID:       {config.station_id}")
        print(f"RPLIDAR Port:     {config.rplidar_port}")
        print(f"RPLIDAR Baudrate: {config.rplidar_baudrate}")
        print(f"RPLIDAR Timeout:  {config.rplidar_timeout}s")
        print(f"Motor PWM:        {config.motor_default_pwm}")
        print(f"Results Dir:      {config.results_directory}")
        
        print("\nScan Rate Test Limits:")
        limits = config.get_test_limits("scan_rate_test")
        for key, value in limits.items():
            print(f"  {key}: {value}")
        
        print("\nAccuracy Tolerance at 1000mm:")
        tolerance = config.get_accuracy_tolerance(1000)
        print(f"  {tolerance}")
        
        print("\n" + "=" * 50)
        print("✓ Configuration loaded successfully!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()