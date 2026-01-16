import os
import json
import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
import platform
import uuid
import logging
import base64

# Configuration
LICENSE_SERVER_URL = os.environ.get('LICENSE_SERVER_URL', 'https://license.printque.ca')

# Use a user-writable location for license files
USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "PrintQueData")
LICENSE_FILE_PATH = os.path.join(USER_DATA_DIR, 'license.key')
CACHE_FILE_PATH = os.path.join(USER_DATA_DIR, '.license_cache')

GRACE_PERIOD_DAYS = 7  # Number of days license remains valid after failing to connect to server
MAX_RETRIES = 3  # Maximum number of connection attempts
RETRY_DELAY = 2  # Seconds to wait between retries

# Add this secret key - KEEP IT SECURE!
HARDWARE_LICENSE_SECRET = "your-hardware-secret-key-change-this"

# Create parent directories for files if they don't exist
os.makedirs(USER_DATA_DIR, exist_ok=True)

# License tiers and their features
LICENSE_TIERS = {
    'FREE': {
        'max_printers': 99,
        'features': ['basic_printing', 'job_queue']
    },
    'STANDARD': {
        'max_printers': 10,  # Updated to 10
        'features': ['basic_printing', 'job_queue', 'advanced_reporting', 'email_notifications']
    },
    'PREMIUM': {
        'max_printers': 20,  # Updated to 20
        'features': ['basic_printing', 'job_queue', 'advanced_reporting', 'email_notifications', 'priority_support']
    },
    'PROFESSIONAL': {
        'max_printers': 50,  # Updated to 50
        'features': ['basic_printing', 'job_queue', 'advanced_reporting', 'email_notifications', 'priority_support', 'api_access']
    },
    'ENTERPRISE': {
        'max_printers': -1,  # Unlimited
        'features': ['basic_printing', 'job_queue', 'advanced_reporting', 'email_notifications', 'priority_support', 'api_access', 'custom_branding', 'multi_tenant']
    }
}

class LicenseError(Exception):
    """Custom exception for license validation errors"""
    pass

def get_machine_id() -> str:
    """Get a unique identifier for this machine."""
    # Implementation depends on OS
    # This is a simplified version
    system_info = platform.node() + platform.machine() + platform.processor()
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, system_info))

def read_license_key() -> str:
    """Read the license key from file."""
    try:
        # First try the user data directory path
        if os.path.exists(LICENSE_FILE_PATH):
            with open(LICENSE_FILE_PATH, 'r') as f:
                return f.read().strip()
        
        # If that fails, try the old path as a fallback for reading
        old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'license.key')
        if os.path.exists(old_path):
            try:
                with open(old_path, 'r') as f:
                    license_key = f.read().strip()
                    # Try to save to the new location for future use
                    save_license_key(license_key)
                    return license_key
            except Exception as e:
                logging.warning(f"Could not read from old license path: {str(e)}")
        
        return ""
    except Exception as e:
        logging.error(f"Error reading license key: {str(e)}")
        return ""

def save_license_key(license_key: str) -> None:
    """Save the license key to file."""
    try:
        # Create parent directory if it doesn't exist
        os.makedirs(os.path.dirname(LICENSE_FILE_PATH), exist_ok=True)
        with open(LICENSE_FILE_PATH, 'w') as f:
            f.write(license_key)
        logging.info(f"License key saved to {LICENSE_FILE_PATH}")
    except Exception as e:
        logging.error(f"Error saving license key: {str(e)}")
        raise

def read_cached_license() -> Dict[str, Any]:
    """Read the cached license information."""
    try:
        with open(CACHE_FILE_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_cached_license(license_data: Dict[str, Any]) -> None:
    """Save license information to cache file."""
    # Create parent directory if it doesn't exist
    os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok=True)
    with open(CACHE_FILE_PATH, 'w') as f:
        json.dump(license_data, f)

def verify_license_with_server(license_key: str) -> Tuple[bool, Dict[str, Any]]:
    """Verify license with the license server."""
    machine_id = get_machine_id()
    hostname = platform.node()
    
    for attempt in range(MAX_RETRIES):
        try:
            logging.info(f"Verifying license with server at {LICENSE_SERVER_URL} (attempt {attempt+1}/{MAX_RETRIES})")
            
            # Updated to match the license server API endpoint
            response = requests.post(
                f"{LICENSE_SERVER_URL}/api/v1/licenses/verify",
                json={
                    'license_key': license_key,
                    'installation_id': machine_id,
                    'hostname': hostname
                },
                timeout=10  # Timeout after 10 seconds
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # If we have a server response, check it for a tier
                if 'tier' in data:
                    tier = data.get('tier', 'FREE').upper()
                    logging.info(f"License verification successful: {tier.lower()} tier")
                    
                    # Handle unknown tiers with a fallback
                    if tier not in LICENSE_TIERS:
                        logging.warning(f"Unknown license tier '{tier}' received, falling back to PROFESSIONAL")
                        tier = 'PROFESSIONAL'  # Choose an appropriate fallback tier
                    
                    # Construct license data from the server response
                    # Treat the presence of a tier as valid, regardless of 'valid' flag
                    license_data = {
                        'valid': True,
                        'tier': tier,
                        'customer': data.get('customer', 'Unknown'),
                        'expires_at': data.get('expires_at'),
                        'last_verified': datetime.now().isoformat(),
                        'features': data.get('features', LICENSE_TIERS[tier]['features']),
                        'max_printers': data.get('max_printers', LICENSE_TIERS[tier]['max_printers'])
                    }
                    
                    # Add days remaining if available
                    if 'days_remaining' in data:
                        license_data['days_remaining'] = data['days_remaining']
                        
                    save_cached_license(license_data)
                    return True, license_data
                else:
                    # No tier in response, consider it an error
                    error_msg = data.get('error', 'License validation failed: No tier information')
                    logging.warning(f"License validation failed: {error_msg}")
                    return False, {'error': error_msg}
            else:
                logging.warning(f"Server returned status code {response.status_code}")
                
                # If this is not the last attempt, wait and retry
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    return False, {'error': f"Server returned status code {response.status_code}"}
                
        except requests.RequestException as e:
            logging.warning(f"Could not connect to license server: {str(e)}.")
            
            # If this is not the last attempt, wait and retry
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            else:
                logging.warning(f"All connection attempts failed. Using fallback.")
                return False, {'error': f"Could not connect to license server after {MAX_RETRIES} attempts: {str(e)}"}
    
    # Should never reach here, but just in case
    return False, {'error': f"Failed to verify license after {MAX_RETRIES} attempts"}

def verify_license_offline(license_key: str) -> Tuple[bool, Dict[str, Any]]:
    """Verify license offline using cached data."""
    cached_license = read_cached_license()
    
    if not cached_license:
        logging.info("No cached license data available. Creating default FREE tier license cache.")
        # If no cached license exists, create a default FREE tier license cache
        default_license = {
            'valid': True,
            'tier': 'FREE',
            'customer': 'Default',
            'expires_at': (datetime.now() + timedelta(days=30)).isoformat(),
            'last_verified': datetime.now().isoformat(),
            'features': LICENSE_TIERS['FREE']['features'],
            'max_printers': LICENSE_TIERS['FREE']['max_printers']
        }
        save_cached_license(default_license)
        return True, default_license
    
    # Check if we're still within the grace period
    last_verified = cached_license.get('last_verified')
    if last_verified:
        last_verified_date = datetime.fromisoformat(last_verified)
        grace_period_end = last_verified_date + timedelta(days=GRACE_PERIOD_DAYS)
        
        if datetime.now() > grace_period_end:
            logging.warning(f"Grace period expired (last verified: {last_verified}). Using FREE tier.")
            # Grace period expired, switch to FREE tier
            free_license = {
                'valid': True,
                'tier': 'FREE',
                'customer': 'Default',
                'expires_at': (datetime.now() + timedelta(days=30)).isoformat(),
                'last_verified': datetime.now().isoformat(),
                'features': LICENSE_TIERS['FREE']['features'],
                'max_printers': LICENSE_TIERS['FREE']['max_printers'],
                'message': 'Grace period expired. Using FREE tier.'
            }
            save_cached_license(free_license)
            return True, free_license
    
    # Handle the case where the cached license tier might not exist in LICENSE_TIERS
    tier = cached_license.get('tier', 'FREE')
    if tier not in LICENSE_TIERS:
        logging.warning(f"Unknown cached license tier '{tier}', falling back to PROFESSIONAL")
        cached_license['tier'] = 'PROFESSIONAL'
        cached_license['features'] = LICENSE_TIERS['PROFESSIONAL']['features']
        cached_license['max_printers'] = LICENSE_TIERS['PROFESSIONAL']['max_printers']
        save_cached_license(cached_license)
    
    logging.info(f"Using cached license data: {cached_license.get('tier', 'FREE')} tier")
    return True, cached_license

def generate_hardware_license(machine_id: str, tier: str, customer: str) -> str:
    """Generate a permanent hardware license."""
    # Create license data
    data = f"{machine_id}|{tier}|{customer}"
    
    # Create signature
    signature = hmac.new(
        HARDWARE_LICENSE_SECRET.encode(),
        data.encode(),
        hashlib.sha256
    ).digest()
    
    # Combine and encode
    full_data = data.encode() + b'||' + signature
    encoded = base64.b64encode(full_data).decode()
    
    # Format as HW-XXXX-XXXX-XXXX
    return f"HW-{encoded[:4]}-{encoded[4:8]}-{encoded[8:]}"

def verify_hardware_license(license_key: str) -> Dict[str, Any]:
    """Verify a hardware license."""
    try:
        # Remove HW- prefix and dashes
        encoded = license_key.replace('HW-', '').replace('-', '')
        
        # Decode
        full_data = base64.b64decode(encoded)
        
        # Split data and signature
        parts = full_data.split(b'||')
        if len(parts) != 2:
            raise ValueError("Invalid format")
        
        data, signature = parts
        
        # Verify signature
        expected_sig = hmac.new(
            HARDWARE_LICENSE_SECRET.encode(),
            data,
            hashlib.sha256
        ).digest()
        
        if not hmac.compare_digest(signature, expected_sig):
            raise ValueError("Invalid signature")
        
        # Parse data
        machine_id, tier, customer = data.decode().split('|')
        
        # Check machine ID
        current_machine = get_machine_id()
        if machine_id != current_machine:
            return {
                'valid': False,
                'tier': 'FREE',
                'features': LICENSE_TIERS['FREE']['features'],
                'max_printers': LICENSE_TIERS['FREE']['max_printers'],
                'message': 'License not valid for this machine'
            }
        
        # Valid license!
        tier = tier.upper()
        if tier not in LICENSE_TIERS:
            tier = 'PROFESSIONAL'
            
        return {
            'valid': True,
            'tier': tier,
            'features': LICENSE_TIERS[tier]['features'],
            'max_printers': LICENSE_TIERS[tier]['max_printers'],
            'customer': customer,
            'type': 'hardware_locked',
            'permanent': True
        }
        
    except Exception as e:
        return {
            'valid': False,
            'tier': 'FREE',
            'features': LICENSE_TIERS['FREE']['features'],
            'max_printers': LICENSE_TIERS['FREE']['max_printers'],
            'message': f'Invalid hardware license: {str(e)}'
        }

def validate_license() -> Dict[str, Any]:
    """Main license validation function with hardware license support."""
    license_key = read_license_key()
    
    if not license_key:
        return {
            'valid': True,
            'tier': 'FREE',
            'features': LICENSE_TIERS['FREE']['features'],
            'max_printers': LICENSE_TIERS['FREE']['max_printers'],
            'message': 'No license key found. Using FREE tier.'
        }
    
    # Check if it's a hardware license (starts with "HW-")
    if license_key.startswith('HW-'):
        return verify_hardware_license(license_key)
    
    # Otherwise, use existing online/offline validation
    # Try online validation first
    logging.info(f"Found license key. Attempting online validation.")
    online_valid, online_result = verify_license_with_server(license_key)
    
    if online_valid:
        # If online validation succeeds, always use that result
        logging.info(f"Online validation successful. Using online license data.")
        return online_result
    
    # ONLY fall back to offline validation if online validation fails
    logging.info(f"Online validation failed. Falling back to offline validation.")
    offline_valid, offline_result = verify_license_offline(license_key)
    
    if offline_valid:
        # Add message to indicate we're using cached data
        return {
            **offline_result,
            'message': 'Using cached license data (offline mode)'
        }
    
    # Both validations failed, create a default FREE tier license cache
    logging.warning(f"Both online and offline validation failed. Using FREE tier.")
    free_license = {
        'valid': True,
        'tier': 'FREE',
        'features': LICENSE_TIERS['FREE']['features'],
        'max_printers': LICENSE_TIERS['FREE']['max_printers'],
        'message': f"License validation failed: {offline_result.get('error', 'Unknown error')}. Using FREE tier."
    }
    save_cached_license(free_license)
    return free_license

def is_feature_enabled(feature_name: str) -> bool:
    """Check if a specific feature is enabled in the current license."""
    license_data = validate_license()
    return feature_name in license_data.get('features', [])

def get_max_printers() -> int:
    """Get the maximum number of printers allowed by the current license."""
    license_data = validate_license()
    return license_data.get('max_printers', LICENSE_TIERS['FREE']['max_printers'])

def get_license_info() -> Dict[str, Any]:
    """Get complete license information."""
    return validate_license()

def update_license(license_key: str) -> Dict[str, Any]:
    """Update the license key and validate it."""
    logging.info(f"Updating license key")
    save_license_key(license_key)
    
    # Clear the cache
    if os.path.exists(CACHE_FILE_PATH):
        logging.info(f"Clearing license cache")
        os.remove(CACHE_FILE_PATH)
    
    # Validate the new license
    return validate_license()

def test_server_connection() -> Dict[str, Any]:
    """
    Test the connection to the license server with improved error handling.
    Will not raise exceptions and always returns a valid result dictionary.
    """
    try:
        # Set a shorter timeout for faster failure
        response = requests.get(
            f"{LICENSE_SERVER_URL}/",
            timeout=3
        )
        return {
            'connected': True,
            'status_code': response.status_code,
            'url': LICENSE_SERVER_URL
        }
    except requests.RequestException as e:
        return {
            'connected': False,
            'error': str(e),
            'url': LICENSE_SERVER_URL
        }
    except Exception as e:
        # Catch any other unexpected errors
        logging.error(f"Unexpected error testing server connection: {str(e)}")
        return {
            'connected': False,
            'error': f"Unexpected error: {str(e)}",
            'url': LICENSE_SERVER_URL
        }

# Helper function to create a free tier license when needed
def _fallback_to_free_tier(error_message: str) -> Dict[str, Any]:
    """Create a fallback FREE tier license when errors occur."""
    logging.warning(f"Using fallback FREE tier due to: {error_message}")
    free_license = {
        'valid': True,
        'tier': 'FREE',
        'features': LICENSE_TIERS['FREE']['features'],
        'max_printers': LICENSE_TIERS['FREE']['max_printers'],
        'message': f'Using FREE tier due to error: {error_message}'
    }
    # Cache this to prevent future errors
    try:
        save_cached_license(free_license)
    except Exception as e:
        logging.error(f"Could not save fallback license to cache: {str(e)}")
    return free_license

def verify_license_startup() -> Dict[str, Any]:
    """Function specifically for startup validation with better error handling."""
    try:
        # Test the server connection first
        try:
            connection_test = test_server_connection()
            if connection_test['connected']:
                logging.info(f"License server is reachable at {LICENSE_SERVER_URL}")
            else:
                logging.warning(f"License server is not reachable at {LICENSE_SERVER_URL}: {connection_test.get('error')}")
                # If we can't connect, don't let this crash the application
                logging.warning("Proceeding with offline validation")
                return _fallback_to_free_tier("Connection to license server failed")
        except Exception as e:
            logging.error(f"Error testing license server connection: {str(e)}")
            return _fallback_to_free_tier(f"Connection error: {str(e)}")
        
        # Wrap the validation in a try block
        try:
            license_data = validate_license()
            return license_data
        except Exception as e:
            logging.error(f"Error during license validation: {str(e)}")
            return _fallback_to_free_tier(f"Validation error: {str(e)}")
            
    except Exception as e:
        logging.error(f"License validation error during startup: {str(e)}")
        # Fallback to FREE tier on any error
        return _fallback_to_free_tier(f"Startup error: {str(e)}")