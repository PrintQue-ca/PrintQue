from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from utils.license_validator import get_license_info, update_license

# Create a Blueprint for license-related routes
license_bp = Blueprint('license', __name__, url_prefix='/license')

# All potential features for display purposes (align with license_validator.py)
ALL_FEATURES = [
    'basic_printing',
    'job_queue',
    'advanced_reporting',
    'email_notifications',
    'priority_support',
    'api_access',
    'custom_branding',
    'multi_tenant'
]

@license_bp.route('/', methods=['GET'])
def license_page():
    """Display the license management page."""
    # Get current license information
    license_info = get_license_info()
    
    # Extract days remaining if available
    days_remaining = license_info.get('days_remaining', None)
    
    # Format expiration date for display
    if 'expires_at' in license_info:
        expires_at_str = license_info['expires_at']
    else:
        expires_at_str = "N/A"
    
    # Add printer usage information
    from services.state import PRINTERS, printers_rwlock, ReadLock
    with ReadLock(printers_rwlock):
        current_printer_count = len(PRINTERS)
    
    license_info['current_printer_count'] = current_printer_count
    
    # Get license tier from app config (this is set at startup)
    tier_from_config = current_app.config.get('LICENSE_TIER', 'FREE')
    max_printers_from_config = current_app.config.get('MAX_PRINTERS', 2)
    
    # Check for any mismatch between current validation and startup validation
    if tier_from_config != license_info.get('tier', 'FREE'):
        flash("License tier has changed since application startup. You may need to restart the application for all changes to take effect.", "warning")
    
    return render_template(
        'license.html',
        license=license_info,
        features=ALL_FEATURES,
        days_remaining=days_remaining,
        expires_at=expires_at_str,
        printer_limit_percent=(current_printer_count / max(1, max_printers_from_config)) * 100
    )

@license_bp.route('/update', methods=['POST'])
def update_license_route():
    """Handle license key update."""
    license_key = request.form.get('license_key', '').strip()
    
    if not license_key:
        flash('Please enter a valid license key.', 'error')
        return redirect(url_for('license.license_page'))
    
    # Update license
    result = update_license(license_key)
    
    if result.get('valid'):
        flash(f"License successfully activated. Tier: {result.get('tier')}", 'success')
        flash("Please restart the application for changes to take effect.", 'info')
    else:
        flash(f"License activation failed: {result.get('message')}", 'error')
    
    return redirect(url_for('license.license_page'))

@license_bp.route('/status', methods=['GET'])
def license_status():
    """API endpoint to get license status (for internal use)."""
    license_info = get_license_info()
    return jsonify(license_info)

# Helper function for blueprint registration
def register_license_routes(app, socketio):
    app.register_blueprint(license_bp)