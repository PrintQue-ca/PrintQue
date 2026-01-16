from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file
import smtplib
import ssl
import os  # Add this import for environment variables
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
from state import PRINTERS, printers_rwlock, ReadLock
from license_validator import get_license_info

# Create a Blueprint for support-related routes
support_bp = Blueprint('support', __name__, url_prefix='/support')

def send_support_email(name, email, subject, message, license_info, system_info):
    """Send support email using Gmail SMTP"""
    try:
        # Email configuration using environment variables for security
        SMTP_SERVER = "smtp.gmail.com"
        SMTP_PORT = 587
        SENDER_EMAIL = os.environ.get('SMTP_EMAIL')
        SENDER_PASSWORD = os.environ.get('SMTP_PASSWORD')
        RECIPIENT_EMAIL = "info@hartleyprinting.com"
        
        # Check if credentials are configured
        if not SENDER_EMAIL or not SENDER_PASSWORD:
            logging.error("SMTP credentials not configured. Set SMTP_EMAIL and SMTP_PASSWORD environment variables.")
            return False, "Email configuration missing. Please contact administrator."
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"PrintQue Support: {subject}"
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECIPIENT_EMAIL
        msg["Reply-To"] = email
        
        # Create email body
        email_body = f"""
PrintQue Support Request
========================

Contact Information:
- Name: {name}
- Email: {email}
- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

License Information:
- Tier: {license_info.get('tier', 'Unknown')}
- Valid: {license_info.get('valid', 'Unknown')}
- Max Printers: {license_info.get('max_printers', 'Unknown')}
- Features: {', '.join(license_info.get('features', []))}

System Information:
- Current Printers: {system_info['printer_count']}
- Application: PrintQue

Subject: {subject}

Message:
{message}

---
This message was sent through the PrintQue support system.
Reply directly to this email to respond to the user.
        """
        
        # Create HTML version
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c5530;">PrintQue Support Request</h2>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <h3 style="margin-top: 0; color: #2c5530;">Contact Information</h3>
                <p><strong>Name:</strong> {name}</p>
                <p><strong>Email:</strong> <a href="mailto:{email}">{email}</a></p>
                <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div style="background-color: #e8f4fd; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <h3 style="margin-top: 0; color: #1e5631;">License Information</h3>
                <p><strong>Tier:</strong> {license_info.get('tier', 'Unknown')}</p>
                <p><strong>Valid:</strong> {license_info.get('valid', 'Unknown')}</p>
                <p><strong>Max Printers:</strong> {license_info.get('max_printers', 'Unknown')}</p>
                <p><strong>Features:</strong> {', '.join(license_info.get('features', []))}</p>
            </div>
            
            <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 10px 0;">
                <h3 style="margin-top: 0; color: #856404;">System Information</h3>
                <p><strong>Current Printers:</strong> {system_info['printer_count']}</p>
                <p><strong>Application:</strong> PrintQue</p>
            </div>
            
            <div style="background-color: #ffffff; padding: 15px; border: 1px solid #ddd; border-radius: 5px; margin: 10px 0;">
                <h3 style="margin-top: 0; color: #2c5530;">Subject</h3>
                <p style="font-weight: bold;">{subject}</p>
                
                <h3 style="color: #2c5530;">Message</h3>
                <div style="background-color: #f9f9f9; padding: 10px; border-left: 4px solid #2c5530;">
                    {message.replace(chr(10), '<br>')}
                </div>
            </div>
            
            <hr style="margin: 20px 0;">
            <p style="font-size: 0.9em; color: #666;">
                This message was sent through the PrintQue support system.<br>
                Reply directly to this email to respond to the user.
            </p>
        </body>
        </html>
        """
        
        # Attach both versions
        text_part = MIMEText(email_body, "plain")
        html_part = MIMEText(html_body, "html")
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Send email
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
            
        return True, "Email sent successfully"
        
    except Exception as e:
        logging.error(f"Failed to send support email: {str(e)}")
        return False, f"Failed to send email: {str(e)}"

@support_bp.route('/', methods=['GET', 'POST'])
def support_page():
    """Display the support page and handle form submission"""
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        # Basic validation
        if not all([name, email, subject, message]):
            flash('Please fill in all fields.', 'error')
            return render_template('support.html')
        
        # Get license and system information
        license_info = get_license_info()
        
        # Get current printer count
        with ReadLock(printers_rwlock):
            current_printer_count = len(PRINTERS)
        
        system_info = {
            'printer_count': current_printer_count
        }
        
        # Send email
        success, error_msg = send_support_email(name, email, subject, message, license_info, system_info)
        
        if success:
            flash('Your support request has been sent successfully. We will respond to your email address shortly.', 'success')
            return redirect(url_for('support.support_page'))
        else:
            flash(f'Failed to send support request: {error_msg}', 'error')
    
    # Get license info for display
    license_info = get_license_info()
    
    return render_template('support.html', license=license_info)

@support_bp.route('/download-logs')
def download_logs():
    """Download logs from the last 5 minutes"""
    try:
        # Import the logger module to access the function
        from logger import get_recent_logs

        # Get logs from the last 5 minutes
        logs_content = get_recent_logs(minutes=5)

        # Create a BytesIO object to serve as a file
        log_buffer = io.BytesIO()
        log_buffer.write(logs_content.encode('utf-8'))
        log_buffer.seek(0)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'printque_logs_{timestamp}.txt'

        # Send the file
        return send_file(
            log_buffer,
            mimetype='text/plain',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logging.error(f"Error downloading logs: {str(e)}")
        flash('Failed to download logs. Please try again.', 'error')
        return redirect(url_for('support.support_page'))

def register_support_routes(app, socketio):
    """Register support routes with the Flask app"""
    app.register_blueprint(support_bp)
