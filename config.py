import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-for-dev-only')
    
    # CRITICAL FIX: Encryption key with fallback
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
    if not ENCRYPTION_KEY:
        # Generate a consistent fallback key based on SECRET_KEY
        import hashlib
        import base64
        # Create a consistent 32-byte key from SECRET_KEY
        key_material = hashlib.sha256(SECRET_KEY.encode()).digest()
        ENCRYPTION_KEY = base64.urlsafe_b64encode(key_material).decode()
        print(f"WARNING: Using generated encryption key. Set ENCRYPTION_KEY in environment for production.")
    
    # Validate encryption key format
    try:
        Fernet(ENCRYPTION_KEY.encode())
    except Exception as e:
        print(f"ERROR: Invalid encryption key: {e}")
        # Generate a new valid key as last resort
        ENCRYPTION_KEY = Fernet.generate_key().decode()
        print("Generated new encryption key. All existing encrypted data will be invalid.")
    
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    
    FILAMENT_DENSITIES = {
        "PLA": 1.25,
        "PETG": 1.27,
        "ABS": 1.04,
    }
    DEFAULT_FILAMENT_DENSITY = 1.25
    
    # UPDATED TIMEOUTS: Reduced to prevent deadlocks
    API_TIMEOUT = 15  # Reduced from 20 to 15 seconds
    UPLOAD_TIMEOUT = 45  # Reduced from 60 to 45 seconds
    STATUS_REFRESH_INTERVAL = 10  # Seconds
    CACHE_TTL = 10  # Seconds
    
    # LOCK TIMEOUTS: New configuration for lock management
    READ_LOCK_TIMEOUT = 5  # Seconds for read locks
    WRITE_LOCK_TIMEOUT = 15  # Seconds for write locks
    SAFE_LOCK_TIMEOUT = 10  # Seconds for SafeLock instances
    
    DEFAULT_END_GCODE = ""  # Default end G-code to pre-fill in UI
    PORT = int(os.getenv('PORT', 5000))  # Added PORT with default 5000
    ADMIN_KEY = os.getenv('ADMIN_KEY', 'default-admin-key-change-me')
    
    # BATCH PROCESSING: Optimized for better performance
    STATUS_BATCH_SIZE = 5  # Reduced from 10 to 5 for faster processing
    STATUS_BATCH_INTERVAL = 1  # Reduced from 2 to 1 second between batches
    MAX_CONCURRENT_JOBS = 5  # Reduced from 10 to prevent overwhelming
    
    # EJECTION SETTINGS: New configuration for ejection behavior
    EJECTION_TIMEOUT_MINUTES = 35  # Maximum time for ejection before forcing completion
    EJECTION_COOLDOWN_SECONDS = 60  # Minimum time between ejections for same printer
    EJECTION_RETRY_ATTEMPTS = 2  # Number of retry attempts for failed ejections
    
    # DISTRIBUTION SETTINGS: Control job distribution behavior
    DISTRIBUTION_INTERVAL = 30  # Seconds between automatic distributions
    DISTRIBUTION_TIMEOUT = 120  # Maximum time for distribution to complete
    
    # Bambu printer configurations
    BAMBU_CA_CERT_PATH = os.path.join(os.path.dirname(__file__), "certs", "bambu_ca.pem")
    BAMBU_MQTT_PORT = 8883
    BAMBU_MQTT_KEEPALIVE = 60
    BAMBU_CONNECTION_TIMEOUT = 20  # Reduced from 30 to 20 seconds
    ENABLE_BAMBU_SUPPORT = True
    BAMBU_FILE_EXTENSION = ".gcode.3mf"
    
    # BAMBU EJECTION SETTINGS: Specific to Bambu printers
    BAMBU_EJECTION_TIMEOUT = 30  # Minutes before forcing Bambu ejection completion
    BAMBU_COMMAND_RETRY_ATTEMPTS = 3  # Retry attempts for Bambu commands
    BAMBU_COMMAND_RETRY_DELAY = 2  # Seconds between Bambu command retries
    
    # DEBUGGING AND MONITORING
    ENABLE_LOCK_MONITORING = True  # Enable lock performance monitoring
    ENABLE_EJECTION_DEBUG = True  # Enable detailed ejection logging
    ENABLE_PERFORMANCE_LOGGING = False  # Enable performance metrics (can be verbose)
    
    # SAFETY FEATURES
    MAX_STUCK_EJECTION_TIME = 40  # Minutes before emergency ejection reset
    EMERGENCY_RESET_THRESHOLD = 10  # Number of stuck printers before emergency reset
    ENABLE_AUTOMATIC_RECOVERY = True  # Enable automatic recovery from stuck states
    
    # WEB INTERFACE SETTINGS
    SOCKET_IO_ASYNC_MODE = 'threading'  # Use threading mode for better stability
    SOCKET_IO_LOGGER = False  # Disable SocketIO logging to reduce noise
    SOCKET_IO_ENGINEIO_LOGGER = False  # Disable EngineIO logging
    
    # FILE HANDLING
    ALLOWED_EXTENSIONS = {'.gcode', '.bgcode', '.3mf', '.gcode.3mf'}
    MAX_FILENAME_LENGTH = 255
    TEMP_FILE_CLEANUP_HOURS = 24  # Hours before cleaning up temp files
    
    # LICENSE CONFIGURATION (if applicable)
    LICENSE_CHECK_INTERVAL = 3600  # Seconds between license checks
    MAX_PRINTERS_FREE = 99
    MAX_PRINTERS_STANDARD = 5
    MAX_PRINTERS_PROFESSIONAL = 15
    MAX_PRINTERS_ENTERPRISE = 999
    
    @classmethod
    def validate_config(cls):
        """Validate configuration settings"""
        issues = []
        
        # Check upload folder
        if not os.path.exists(cls.UPLOAD_FOLDER):
            try:
                os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
            except Exception as e:
                issues.append(f"Cannot create upload folder: {e}")
        
        # Check Bambu certificate if Bambu support is enabled
        if cls.ENABLE_BAMBU_SUPPORT and not os.path.exists(cls.BAMBU_CA_CERT_PATH):
            issues.append(f"Bambu CA certificate not found: {cls.BAMBU_CA_CERT_PATH}")
        
        # Validate timeout values
        if cls.API_TIMEOUT < 5:
            issues.append("API_TIMEOUT should be at least 5 seconds")
        
        if cls.READ_LOCK_TIMEOUT >= cls.WRITE_LOCK_TIMEOUT:
            issues.append("READ_LOCK_TIMEOUT should be less than WRITE_LOCK_TIMEOUT")
        
        # Validate ejection settings
        if cls.EJECTION_TIMEOUT_MINUTES < 5:
            issues.append("EJECTION_TIMEOUT_MINUTES should be at least 5 minutes")
        
        return issues
    
    @classmethod
    def get_timeout_config(cls):
        """Get timeout configuration for easy access"""
        return {
            'api_timeout': cls.API_TIMEOUT,
            'upload_timeout': cls.UPLOAD_TIMEOUT,
            'read_lock_timeout': cls.READ_LOCK_TIMEOUT,
            'write_lock_timeout': cls.WRITE_LOCK_TIMEOUT,
            'safe_lock_timeout': cls.SAFE_LOCK_TIMEOUT,
            'ejection_timeout_minutes': cls.EJECTION_TIMEOUT_MINUTES,
            'distribution_timeout': cls.DISTRIBUTION_TIMEOUT,
        }
    
    @classmethod
    def get_ejection_config(cls):
        """Get ejection-specific configuration"""
        return {
            'timeout_minutes': cls.EJECTION_TIMEOUT_MINUTES,
            'cooldown_seconds': cls.EJECTION_COOLDOWN_SECONDS,
            'retry_attempts': cls.EJECTION_RETRY_ATTEMPTS,
            'max_stuck_time': cls.MAX_STUCK_EJECTION_TIME,
            'enable_debug': cls.ENABLE_EJECTION_DEBUG,
        }

# Validate configuration on import
if __name__ != "__main__":
    validation_issues = Config.validate_config()
    if validation_issues:
        print("Configuration validation issues:")
        for issue in validation_issues:
            print(f"  - {issue}")