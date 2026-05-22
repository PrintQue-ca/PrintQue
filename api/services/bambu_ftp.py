"""
Bambu FTP Upload Module for PrintQue
Handles file uploads to Bambu printers via FTPS on port 990
"""
import logging
import os
import re
import socket
import ssl
import time
from typing import Optional, Tuple, TypedDict

from services.state import decrypt_api_key

logger = logging.getLogger(__name__)


class BambuUploadPaths(TypedDict):
    """Paths on the printer after FTP upload — use these for MQTT print start."""

    stor_path: str
    gcode_param: str
    project_url: str


def paths_for_stor(stor_path: str) -> BambuUploadPaths:
    """
    MQTT paths for a file uploaded via FTP.

    Files are stored at the FTP root (bare filename). On P1/P1S firmware that
    location is exposed as ``/sdcard/<name>`` for print commands.
    """
    name = os.path.basename(stor_path.replace('\\', '/'))
    printer_path = f'/sdcard/{name}'
    return {
        'stor_path': name,
        'gcode_param': printer_path,
        'project_url': f'file://{printer_path}',
    }


def normalize_bambu_remote_filename(filename: str) -> str:
    """Return the filename Bambu expects on printer storage (not *.gcode.3mf)."""
    name = os.path.basename(filename)
    lower = name.lower()
    if lower.endswith('.gcode.3mf'):
        fixed = name[: -len('.gcode.3mf')] + '.3mf'
        if fixed != name:
            logger.info(f"Normalized Bambu remote filename: {name} -> {fixed}")
        return fixed
    return name


def bambu_ftp_stor_path(remote_filename: str) -> str:
    """FTP STOR target at printer root (legacy PrintQue behavior)."""
    return normalize_bambu_remote_filename(remote_filename)


def bambu_project_file_url(remote_filename: str) -> str:
    """MQTT project_file URL after a root FTP upload."""
    return paths_for_stor(bambu_ftp_stor_path(remote_filename))['project_url']


def prepare_gcode_for_bambu(filepath: str, upload_folder: str) -> Tuple[bool, str, str]:
    """
    Prepare a G-code file for Bambu printer upload.

    Returns:
        Tuple of (success, prepared_filepath, remote_filename)
    """
    try:
        filename = os.path.basename(filepath)
        lower = filename.lower()
        if lower.endswith('.gcode'):
            remote_filename = filename
        elif lower.endswith('.3mf'):
            remote_filename = normalize_bambu_remote_filename(filename)
        else:
            remote_filename = f"{filename}.gcode"
            logger.info(f"Added .gcode extension: {filename} -> {remote_filename}")

        return True, filepath, remote_filename

    except Exception as e:
        logger.error(f"Error preparing file for Bambu: {str(e)}")
        return False, "", ""


def upload_to_bambu(
    printer: dict,
    local_file: str,
    remote_name: Optional[str] = None,
) -> Tuple[bool, str, Optional[BambuUploadPaths]]:
    """
    Upload a file to the printer FTP root via FTPS.

    Returns:
        (success, message, paths) — paths is set only on success.
    """
    printer_ip = printer['ip']
    printer_name = printer['name']

    try:
        access_code = decrypt_api_key(printer['access_code'])
        if not access_code:
            return False, "Failed to decrypt access code", None
    except Exception as e:
        logger.error(f"Error decrypting access code: {str(e)}")
        return False, f"Failed to decrypt access code: {str(e)}", None

    if not os.path.exists(local_file):
        error_msg = f"File not found: {local_file}"
        logger.error(error_msg)
        return False, error_msg, None

    file_size = os.path.getsize(local_file)
    if not remote_name:
        remote_name = os.path.basename(local_file)
    remote_name = normalize_bambu_remote_filename(remote_name)
    stor_path = remote_name
    upload_paths = paths_for_stor(stor_path)

    logger.info(f"Starting FTP upload to Bambu printer {printer_name} at {printer_ip}")

    try:
        sock = socket.create_connection((printer_ip, 990), timeout=30)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.maximum_version = ssl.TLSVersion.TLSv1_2
        secure_sock = ssl_context.wrap_socket(sock, server_hostname=printer_ip)

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

        def send_command(cmd):
            logger.debug(f"Sending: {cmd}")
            secure_sock.send((cmd + "\r\n").encode('latin-1'))
            response = read_response()
            logger.debug(f"Received: {response}")
            return response

        read_response()

        response = send_command("USER bblp")
        if not response.startswith('331'):
            raise Exception(f"USER command failed: {response}")

        response = send_command(f"PASS {access_code}")
        if not response.startswith('230'):
            raise Exception(f"Login failed: {response}")

        logger.info(f"Successfully logged into Bambu printer {printer_name}")

        response = send_command("PROT P")
        if not response.startswith('200'):
            logger.warning(f"PROT P warning: {response}")

        response = send_command("TYPE I")
        if not response.startswith('200'):
            raise Exception(f"TYPE I failed: {response}")

        response = send_command("PASV")
        if not response.startswith('227'):
            raise Exception(f"PASV failed: {response}")

        match = re.search(r'\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)', response)
        if not match:
            raise Exception(f"Could not parse PASV response: {response}")

        data_host = f"{match.group(1)}.{match.group(2)}.{match.group(3)}.{match.group(4)}"
        data_port = int(match.group(5)) * 256 + int(match.group(6))

        logger.info(
            f"Bambu {printer_name}: uploading to FTP root as {stor_path} "
            f"(print url={upload_paths['project_url']})"
        )

        send_command(f"STOR {stor_path}")

        data_sock = socket.create_connection((data_host, data_port), timeout=30)
        data_ssl_sock = ssl_context.wrap_socket(
            data_sock,
            server_hostname=printer_ip,
            session=secure_sock.session,
        )

        logger.info(
            f"Uploading {os.path.basename(local_file)} ({file_size:,} bytes) "
            f"to {printer_name}..."
        )

        bytes_sent = 0
        start_time = time.time()
        with open(local_file, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                data_ssl_sock.send(chunk)
                bytes_sent += len(chunk)

        data_ssl_sock.close()
        data_sock.close()

        response = read_response()
        if not response.startswith('226'):
            logger.warning(f"Unexpected STOR response: {response}")

        elapsed_time = time.time() - start_time
        transfer_rate = bytes_sent / elapsed_time / 1024 / 1024 if elapsed_time > 0 else 0
        logger.info(
            f"Upload successful! Transferred {bytes_sent:,} bytes in "
            f"{elapsed_time:.1f} seconds ({transfer_rate:.1f} MB/s)"
        )

        response = send_command(f"SIZE {stor_path}")
        if response.startswith('213'):
            remote_size = int(response.split()[1])
            if remote_size == file_size:
                logger.debug(f"Verified: {stor_path} ({remote_size:,} bytes) on printer")
            else:
                logger.warning(
                    f"Size mismatch for {stor_path}: local={file_size}, remote={remote_size}"
                )

        send_command("QUIT")
        secure_sock.close()
        sock.close()

        logger.info(
            f"Successfully uploaded {stor_path} to {printer_name} "
            f"(project_url={upload_paths['project_url']})"
        )
        return True, f"Successfully uploaded {stor_path}", upload_paths

    except Exception as e:
        error_msg = f"FTP upload failed: {str(e)}"
        logger.error(error_msg)
        return False, error_msg, None
