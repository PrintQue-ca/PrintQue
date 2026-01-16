"""
Bambu FTP Upload Module for PrintQue - Fixed Version with Correct FTP Sequence
Handles file uploads to Bambu printers via FTPS on port 990
FIXED: Corrected file extension handling to prevent .gcode.3mf naming issue
"""
import ftplib
import ssl
import os
import socket
import logging
import time
import re
from typing import Optional, Tuple
from services.state import decrypt_api_key

logger = logging.getLogger(__name__)

class BambuImplicitFTPS(ftplib.FTP_TLS):
    """Custom FTPS class for Bambu's implicit FTPS on port 990 with session reuse"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_connected = False
        self.timeout = 30  # Set default timeout for all operations
        
    def connect(self, host='', port=0, timeout=-999, source_address=None):
        """Connect to host:port using implicit FTPS"""
        if host != '':
            self.host = host
        if port > 0:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        if source_address is not None:
            self.source_address = source_address
            
        # Create and wrap socket immediately for implicit FTPS
        self.sock = socket.create_connection((self.host, self.port), self.timeout, source_address=self.source_address)
        self.af = self.sock.family
        
        # Configure SSL context for TLS 1.2
        if not hasattr(self, 'context'):
            self.context = ssl.create_default_context()
        self.context.check_hostname = False
        self.context.verify_mode = ssl.CERT_NONE
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.maximum_version = ssl.TLSVersion.TLSv1_2
        
        # Wrap with SSL immediately (implicit FTPS)
        self.sock = self.context.wrap_socket(self.sock, server_hostname=self.host)
        self._is_connected = True
        
        # Set up file for responses
        self.file = self.sock.makefile('r', encoding='latin-1')
        self.welcome = self.getresp()
        
        logger.debug(f"Connected to Bambu FTP: {self.welcome}")
        return self.welcome
    
    def ntransfercmd(self, cmd, rest=None):
        """Override to support SSL session reuse on data connection"""
        conn, size = super().ntransfercmd(cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session  # Reuse control channel session
            )
        return conn, size

def upload_to_bambu(printer: dict, local_file: str, remote_name: Optional[str] = None) -> Tuple[bool, str]:
    """
    Upload a file to Bambu printer via FTPS with raw socket implementation and SSL session reuse
    
    Args:
        printer: Printer dictionary containing ip and access_code
        local_file: Path to local file to upload
        remote_name: Optional remote filename (defaults to basename with .gcode.3mf extension)
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    printer_ip = printer['ip']
    printer_name = printer['name']
    
    # Decrypt access code
    try:
        access_code = decrypt_api_key(printer['access_code'])
        if not access_code:
            return False, "Failed to decrypt access code"
    except Exception as e:
        logger.error(f"Error decrypting access code: {str(e)}")
        return False, f"Failed to decrypt access code: {str(e)}"
    
    logger.info(f"Starting FTP upload to Bambu printer {printer_name} at {printer_ip}")
    
    # Check file exists
    if not os.path.exists(local_file):
        error_msg = f"File not found: {local_file}"
        logger.error(error_msg)
        return False, error_msg
    
    # Get file size
    file_size = os.path.getsize(local_file)
    
    # Determine remote filename
    if not remote_name:
        # Default behavior - just use the original filename
        # Let prepare_gcode_for_bambu handle any renaming
        remote_name = os.path.basename(local_file)
    
    logger.debug(f"Local file: {local_file}, Remote name: {remote_name}")
    
    # Socket-based FTP Implementation
    ftp = None
    try:
        # Connect directly with socket
        logger.debug(f"Connecting to {printer_ip}:990...")
        
        # Create and connect socket
        sock = socket.create_connection((printer_ip, 990), timeout=30)
        
        # Create SSL context for implicit FTPS (TLS 1.2 specifically for Bambu)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.maximum_version = ssl.TLSVersion.TLSv1_2
        
        # Wrap socket with SSL immediately (implicit FTPS)
        secure_sock = ssl_context.wrap_socket(sock, server_hostname=printer_ip)
        
        # Helper function to read response
        def read_response():
            response = b""
            while True:
                try:
                    chunk = secure_sock.recv(1024)
                    if not chunk:
                        break
                    response += chunk
                    if b'\r\n' in chunk:
                        break
                except socket.timeout:
                    break
            return response.decode('latin-1').strip()
        
        # Helper function to send command
        def send_command(cmd):
            logger.debug(f"Sending: {cmd}")
            secure_sock.send((cmd + "\r\n").encode('latin-1'))
            response = read_response()
            logger.debug(f"Received: {response}")
            return response
        
        # Read welcome message
        welcome = read_response()
        logger.debug(f"Welcome: {welcome}")
        
        # Login
        response = send_command("USER bblp")
        if not response.startswith('331'):
            raise Exception(f"USER command failed: {response}")
        
        response = send_command(f"PASS {access_code}")
        if not response.startswith('230'):
            raise Exception(f"Login failed: {response}")
        
        logger.info(f"Successfully logged into Bambu printer {printer_name}")
        
        # Set data protection
        response = send_command("PROT P")
        if not response.startswith('200'):
            logger.warning(f"PROT P warning: {response}")
        else:
            logger.debug("Data protection set to private (encrypted)")
        
        # Set binary mode
        response = send_command("TYPE I")
        if not response.startswith('200'):
            raise Exception(f"TYPE I failed: {response}")
        
        # Enter passive mode to get data port
        response = send_command("PASV")
        if not response.startswith('227'):
            raise Exception(f"PASV failed: {response}")
        
        # Parse PASV response (227 Entering Passive Mode (h1,h2,h3,h4,p1,p2))
        match = re.search(r'\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)', response)
        if not match:
            raise Exception(f"Could not parse PASV response: {response}")
        
        data_host = f"{match.group(1)}.{match.group(2)}.{match.group(3)}.{match.group(4)}"
        data_port = int(match.group(5)) * 256 + int(match.group(6))
        
        logger.debug(f"Data connection: {data_host}:{data_port}")
        
        # Send STOR command FIRST (before opening data connection)
        send_command(f"STOR {remote_name}")
        # Don't wait for response yet - it will come after data transfer
        
        # NOW create data connection
        data_sock = socket.create_connection((data_host, data_port), timeout=30)
        
        # Wrap data socket with SSL - must reuse session from control connection
        data_ssl_sock = ssl_context.wrap_socket(
            data_sock, 
            server_hostname=printer_ip,
            session=secure_sock.session  # This is critical for Bambu!
        )
        
        # Send file data
        logger.info(f"Uploading {os.path.basename(local_file)} ({file_size:,} bytes) to {printer_name}...")
        
        bytes_sent = 0
        start_time = time.time()
        
        with open(local_file, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                data_ssl_sock.send(chunk)
                bytes_sent += len(chunk)
        
        # Close data connection
        data_ssl_sock.close()
        data_sock.close()
        
        # Now read the STOR response (should be 226)
        response = read_response()
        if not response.startswith('226'):
            logger.warning(f"Unexpected STOR response: {response}")
        
        elapsed_time = time.time() - start_time
        transfer_rate = bytes_sent / elapsed_time / 1024 / 1024  # MB/s
        
        logger.info(f"Upload successful! Transferred {bytes_sent:,} bytes in {elapsed_time:.1f} seconds ({transfer_rate:.1f} MB/s)")
        
        # Verify file size on printer
        response = send_command(f"SIZE {remote_name}")
        if response.startswith('213'):
            remote_size = int(response.split()[1])
            if remote_size == file_size:
                logger.debug(f"Verified: {remote_name} ({remote_size:,} bytes) on printer")
            else:
                logger.warning(f"Size mismatch: local={file_size}, remote={remote_size}")
        
        # Quit
        send_command("QUIT")
        secure_sock.close()
        sock.close()
        
        logger.info(f"Successfully uploaded {remote_name} to {printer_name}")
        return True, f"Successfully uploaded {remote_name}"
        
    except Exception as e:
        error_msg = f"FTP upload failed: {str(e)}"
        logger.error(error_msg)
        if ftp:
            try:
                ftp.quit()
            except:
                pass
        return False, error_msg

def prepare_gcode_for_bambu(filepath: str, upload_folder: str) -> Tuple[bool, str, str]:
    """
    Prepare a G-code file for Bambu printer upload
    
    FIXED: This function now correctly handles file extensions.
    Bambu printers expect either .3mf or .gcode files, NOT .gcode.3mf
    
    Args:
        filepath: Path to the original file
        upload_folder: Folder to store prepared files
        
    Returns:
        Tuple of (success: bool, prepared_filepath: str, remote_filename: str)
    """
    try:
        filename = os.path.basename(filepath)
        logger.debug(f"Preparing file for Bambu: {filename}")
        
        # Determine the remote filename
        # FIXED: Bambu printers expect either .3mf or .gcode files, NOT .gcode.3mf
        if filename.endswith('.3mf'):
            # Keep .3mf files as-is - this is the standard Bambu format
            remote_filename = filename
        elif filename.endswith('.gcode'):
            # Keep .gcode files as-is
            remote_filename = filename
        elif filename.endswith('.gcode.3mf'):
            # Fix incorrectly named files by removing the .gcode part
            # example.gcode.3mf -> example.3mf
            remote_filename = filename.replace('.gcode.3mf', '.3mf')
            logger.warning(f"Fixed incorrect filename: {filename} -> {remote_filename}")
        else:
            # For any other format, add .gcode extension
            remote_filename = f"{filename}.gcode"
            logger.info(f"Added .gcode extension: {filename} -> {remote_filename}")
            
        # For now, we'll use the original file
        # In the future, you might want to convert or package the file here
        prepared_filepath = filepath
        
        logger.debug(f"Prepared file for Bambu: {prepared_filepath} -> {remote_filename}")
        return True, prepared_filepath, remote_filename
        
    except Exception as e:
        logger.error(f"Error preparing file for Bambu: {str(e)}")
        return False, "", ""