#!/usr/bin/env python3
##Script function and purpose: FreeBSD Bluetooth Daemon.
##This script serves as the privileged backend for the bt-tui Bluetooth management system.
##It runs as root to interface with FreeBSD's native Bluetooth stack, which includes:
##  - hccontrol: The Host Controller Interface control utility for device discovery and management
##  - hcsecd: The Bluetooth security daemon that handles device pairing and authentication
##  - netgraph: FreeBSD's kernel-level graph-based networking subsystem used for Bluetooth
##The daemon exposes a Unix Domain Socket API at /var/run/bt-tui.sock for the unprivileged
##TUI client to communicate with. This privilege separation ensures that the user-facing
##application never needs root access directly, improving system security.
##
##Supported Commands (via JSON IPC):
##  - {"action": "scan"} - Discover nearby Bluetooth devices using hccontrol inquiry
##  - {"action": "pair", "mac": "XX:XX:XX:XX:XX:XX", "pin": "0000"} - Pair with a device
##
##FreeBSD-Specific Notes:
##  - Requires ng_ubt kernel module loaded for USB Bluetooth adapters
##  - Uses ubt0hci as the default HCI device name (configurable via --device)
##  - Manages /etc/bluetooth/hcsecd.conf for persistent pairing information

import os
import sys
import socket
import json
import logging
import subprocess
import signal
import stat
import argparse
from utils import SOCKET_PATH, BUFFER_SIZE

##Step purpose: Define constants and global configurations for the daemon.
##These paths follow FreeBSD conventions:
##  - /var/run/ for runtime socket files (cleaned on reboot)
##  - /var/log/ for persistent log files
##  - /etc/bluetooth/ for Bluetooth configuration (FreeBSD standard location)
LOG_PATH = "/var/log/bt-tui-daemon.log"
HCSECD_CONF_PATH = "/etc/bluetooth/hcsecd.conf"
DEFAULT_HCI_DEVICE = "ubt0hci"

# Global variable to store the configured HCI device
hci_device = DEFAULT_HCI_DEVICE


##Function purpose: Set up logging configuration for the daemon.
##Configures dual logging to both console (for interactive debugging) and file
##(for persistent logging and troubleshooting). Uses FreeBSD's standard /var/log/
##location for log files, with fallback to current directory for development.
def setup_logging():
    ##Step purpose: Initialize with console handler for immediate feedback.
    ##StreamHandler outputs to stderr, visible when running daemon interactively.
    handlers = [logging.StreamHandler()]
    
    ##Step purpose: Attempt to add file handler for persistent logging.
    ##The try/except handles cases where /var/log is not writable (non-root testing).
    try:
        ##Action purpose: Create file handler at standard FreeBSD log location.
        handlers.append(logging.FileHandler(LOG_PATH))
    except PermissionError:
        ##Fallback purpose: Log to local directory if /var/log is not writable.
        ##This enables development and testing without root privileges.
        handlers.append(logging.FileHandler("./bt-tui-daemon.log"))
    
    ##Step purpose: Configure the logging format and level.
    ##INFO level captures operational messages without excessive debug noise.
    ##Format includes timestamp for log analysis and troubleshooting.
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

##Function purpose: Ensure the script is running with root privileges.
##This security check is critical because FreeBSD's Bluetooth stack requires root access:
##  - hccontrol commands access /dev/ubtN devices (root-only by default)
##  - Writing to /etc/bluetooth/hcsecd.conf requires root
##  - Restarting hcsecd service requires root privileges
##If not running as root, the daemon exits immediately with an error message.
def check_root():
    ##Condition purpose: Check if the effective user ID is 0 (root).
    ##os.geteuid() returns the effective UID, which handles sudo/su cases correctly.
    ##We use euid (not uid) because setuid binaries may have different effective privileges.
    if os.geteuid() != 0:
        ##Action purpose: Log error and exit if not root.
        ##Exit code 1 indicates abnormal termination due to privilege issue.
        logging.error("The daemon must be run as root.")
        sys.exit(1)

##Function purpose: Parse output from hccontrol inquiry command and extract device information.
##FreeBSD's hccontrol inquiry command output format varies depending on the Bluetooth
##adapter and firmware. This parser handles multiple common formats:
##  - Simple format: Just MAC addresses on separate lines
##  - Verbose format: "BD_ADDR: XX:XX:XX:XX:XX:XX" with additional device info
##  - Labeled format: "Inquiry result #N" followed by device details
##
##The function extracts MAC addresses by looking for the characteristic colon-separated
##format (XX:XX:XX:XX:XX:XX) with exactly 5 colons.
##
##Returns: List of device dictionaries with keys: mac, name, rssi, paired, connected
def parse_inquiry_output(stdout_text):
    ##Step purpose: Initialize empty list to collect discovered devices.
    devices = []
    
    ##Step purpose: Split output into lines for line-by-line processing.
    ##strip() removes leading/trailing whitespace from the entire output.
    lines = stdout_text.strip().split('\n')
    
    ##Loop purpose: Iterate through each line of hccontrol output.
    for line in lines:
        ##Condition purpose: Skip empty lines and header lines.
        ##Header lines typically start with "Inquiry result" and contain metadata.
        if not line.strip() or line.startswith('Inquiry result'):
            continue
        
        ##Step purpose: Parse device information from output line.
        ##Look for lines containing BD_ADDR label or raw MAC addresses.
        if 'BD_ADDR' in line or ':' in line:
            ##Action purpose: Split line into whitespace-separated parts.
            parts = line.split()
            mac = None
            
            ##Loop purpose: Find the part that looks like a MAC address.
            ##MAC addresses have exactly 5 colons (6 hex octets separated by colons).
            for part in parts:
                ##Condition purpose: Identify MAC address by counting colons.
                if part.count(':') == 5:
                    mac = part
                    break
            
            ##Condition purpose: Only create device entry if valid MAC found.
            if mac:
                ##Step purpose: Create device dictionary with discovered info.
                ##Default values used for name, rssi since inquiry doesn't provide them.
                ##paired/connected status would require additional hccontrol commands.
                device = {
                    "mac": mac,
                    "name": "Unknown",
                    "rssi": -99,
                    "paired": False,
                    "connected": False
                }
                devices.append(device)
    
    ##Return purpose: Provide list of discovered devices to caller.
    return devices

##Function purpose: Execute Bluetooth device discovery using FreeBSD's hccontrol utility.
##This function wraps the hccontrol inquiry command which sends HCI Inquiry commands
##to discover nearby Bluetooth devices in discoverable mode.
##
##FreeBSD-Specific Details:
##  - Uses the configured HCI node (default 'ubt0hci')
##  - The inquiry command sends Bluetooth inquiry packets for ~10 seconds
##  - Results include MAC addresses of discovered devices
##  - Timeout set to 30 seconds to allow for slow/congested environments
##
##Returns: Dictionary with status, optional message, and data (list of devices)
def scan_devices():
    ##Action purpose: Execute hccontrol inquiry command to discover Bluetooth devices.
    ##Using subprocess.run with capture_output for clean stdout/stderr handling.
    try:
        ##Step purpose: Call hccontrol with inquiry subcommand.
        ##-n <hci_device> specifies the netgraph node name for the HCI device.
        ##timeout=30 prevents hanging if Bluetooth stack is unresponsive.
        logging.info(f"Scanning on device: {hci_device}")
        result = subprocess.run(
            ['hccontrol', '-n', hci_device, 'inquiry'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        ##Condition purpose: Check if command execution was successful.
        ##Non-zero return code indicates hccontrol encountered an error.
        if result.returncode != 0:
            ##Action purpose: Log the error and return failure response.
            logging.error(f"hccontrol inquiry failed: {result.stderr}")
            return {"status": "error", "message": "Failed to scan devices", "data": []}
        
        ##Step purpose: Parse the output to extract device information.
        ##The parse_inquiry_output function handles various output formats.
        devices = parse_inquiry_output(result.stdout)
        
        ##Action purpose: Log successful scan with device count.
        logging.info(f"Scan completed: found {len(devices)} devices")
        return {"status": "success", "data": devices}
    
    ##Error purpose: Handle subprocess execution errors with specific messages.
    except subprocess.TimeoutExpired:
        ##Error purpose: Handle case where inquiry takes too long.
        ##This can happen if Bluetooth hardware is frozen or overloaded.
        logging.error("hccontrol inquiry timed out")
        return {"status": "error", "message": "Scan timeout", "data": []}
    except FileNotFoundError:
        ##Error purpose: Handle case where hccontrol binary is not found.
        ##This indicates FreeBSD Bluetooth tools are not installed or not in PATH.
        logging.error("hccontrol command not found")
        return {"status": "error", "message": "hccontrol not found", "data": []}
    except Exception as e:
        ##Error purpose: Catch-all for unexpected errors during scanning.
        logging.error(f"Scan error: {str(e)}")
        return {"status": "error", "message": str(e), "data": []}

##Function purpose: Update hcsecd.conf with a new device entry for Bluetooth pairing.
##FreeBSD's hcsecd (Bluetooth Security Daemon) reads device pairing information from
##/etc/bluetooth/hcsecd.conf. This function adds new device entries to enable pairing.
##
##hcsecd.conf Format:
##  device {
##      bdaddr  XX:XX:XX:XX:XX:XX;
##      name    "Device Name";
##      key     nokey;            # or actual link key after pairing
##      pin     "0000";           # PIN code for legacy pairing
##  }
##
##Parameters:
##  conf_path: Path to hcsecd.conf (typically /etc/bluetooth/hcsecd.conf)
##  mac: Bluetooth MAC address of the device to pair
##  pin: PIN code for pairing (default "0000" for most audio devices)
##  name: Human-readable device name (optional)
##
##Returns: True if config was updated, False if device already exists or error
def update_hcsecd_conf(conf_path, mac, pin, name="Unknown"):
    ##Error purpose: Wrap file operations in try/except for robust error handling.
    try:
        ##Condition purpose: Check if config file exists, create if not.
        ##This handles fresh FreeBSD installations without Bluetooth config.
        if not os.path.exists(conf_path):
            ##Action purpose: Create new hcsecd.conf with header comment.
            with open(conf_path, "w") as f:
                f.write("# hcsecd.conf generated by bt-tui\n")
        
        ##Step purpose: Read current config to check for existing entries.
        with open(conf_path, "r") as f:
            content = f.read()
        
        ##Condition purpose: Check if device already exists in config.
        ##Simple substring check - if MAC is in file, device was already added.
        if mac in content:
            ##Action purpose: Log and return False for duplicate device.
            logging.info(f"Device {mac} already in hcsecd.conf")
            return False

        ##Step purpose: Build new device entry in hcsecd.conf format.
        ##Uses tabs for formatting to match FreeBSD's standard config style.
        ##'nokey' means we don't have the link key yet - hcsecd will negotiate it.
        entry = f"\ndevice {{\n\tbdaddr\t{mac};\n\tname\t\"{name}\";\n\tkey\tnokey;\n\tpin\t\"{pin}\";\n}}\n"
        
        ##Action purpose: Append new entry to config file.
        with open(conf_path, "a") as f:
            f.write(entry)
        
        ##Action purpose: Log successful config update.
        logging.info(f"Added device {mac} to {conf_path}")
        return True
    
    ##Error purpose: Handle any file I/O or permission errors.
    except Exception as e:
        logging.error(f"Failed to update hcsecd.conf: {e}")
        return False

##Function purpose: Restart the hcsecd service to apply configuration changes.
##After modifying /etc/bluetooth/hcsecd.conf, the hcsecd daemon must be restarted
##to read the new configuration and enable pairing with newly added devices.
##
##FreeBSD Service Management:
##  - Uses FreeBSD's rc.d service management system
##  - 'service hcsecd restart' stops and starts the daemon
##  - hcsecd must be enabled in /etc/rc.conf (hcsecd_enable="YES")
##
##Returns: True if service restarted successfully, False otherwise
def restart_hcsecd_service():
    ##Error purpose: Wrap service command in try/except for error handling.
    try:
        ##Action purpose: Log service restart attempt for debugging.
        logging.info("Restarting hcsecd service...")
        
        ##Step purpose: Execute FreeBSD service command to restart hcsecd.
        ##Using subprocess.run for clean execution with output capture.
        result = subprocess.run(
            ['service', 'hcsecd', 'restart'],
            capture_output=True,
            text=True
        )
        
        ##Condition purpose: Check if service restart was successful.
        if result.returncode == 0:
            ##Action purpose: Log successful restart.
            logging.info("hcsecd restarted successfully")
            return True
        else:
            ##Action purpose: Log failure with stderr output for debugging.
            ##Common failures: service not enabled, permission denied, config syntax error.
            logging.error(f"Failed to restart hcsecd: {result.stderr}")
            return False
    
    ##Error purpose: Handle unexpected errors during service restart.
    except Exception as e:
        logging.error(f"Error restarting hcsecd: {e}")
        return False

##Function purpose: Process incoming client requests and route to appropriate handlers.
##This is the central command router for the daemon's IPC protocol. It extracts
##the action field from incoming JSON requests and dispatches to the appropriate
##handler function.
##
##Supported Actions:
##  - "scan": Discover nearby Bluetooth devices
##  - "pair": Pair with a specific device (requires mac, optional pin)
##
##Parameters:
##  command_data: Dictionary containing the parsed JSON request
##
##Returns: Dictionary response with status and relevant data/message
def handle_command(command_data):
    ##Step purpose: Extract action from the command data.
    ##Default to empty string if action key is missing.
    action = command_data.get("action", "")
    
    ##Action purpose: Log incoming command for debugging and audit trail.
    logging.info(f"Handling command: {action}")
    
    ##Condition purpose: Route to scan handler for device discovery.
    if action == "scan":
        ##Action purpose: Execute device scan and return results.
        return scan_devices()
    
    ##Condition purpose: Route to pair handler for device pairing.
    elif action == "pair":
        ##Step purpose: Extract pairing parameters from command.
        mac = command_data.get("mac", "")
        pin = command_data.get("pin", "0000")
        
        ##Condition purpose: Validate that MAC address was provided.
        if not mac:
            return {"status": "error", "message": "No MAC address provided"}
        
        ##Step purpose: Update hcsecd.conf and restart service.
        ##Two-step process: first update config, then restart daemon.
        if update_hcsecd_conf(HCSECD_CONF_PATH, mac, pin):
            ##Condition purpose: Check if service restart was successful.
            if restart_hcsecd_service():
                return {"status": "success", "message": f"Paired with {mac}"}
            else:
                ##Warning purpose: Config updated but service failed to restart.
                ##User may need to manually restart hcsecd.
                return {"status": "warning", "message": "Config updated but service restart failed"}
        else:
            ##Error purpose: Config update failed (device exists or file error).
            return {"status": "error", "message": "Failed to update configuration (or already paired)"}
    
    ##Condition purpose: Handle unknown or unsupported commands.
    else:
        ##Action purpose: Log warning for unknown commands (potential client bug or attack).
        logging.warning(f"Unknown command: {action}")
        return {"status": "error", "message": f"Unknown action: {action}"}

##Function purpose: Handle individual client connection and process requests.
##This function manages the lifecycle of a single client connection:
##  1. Receive data from the client socket
##  2. Parse the JSON request
##  3. Route to appropriate command handler
##  4. Send JSON response back to client
##  5. Close the connection
##
##The function uses a try/finally pattern to ensure the client socket is always
##closed, even if an error occurs during processing.
##
##Parameters:
##  client_socket: Connected socket object for the client
def handle_client_connection(client_socket):
    ##Error purpose: Ensure proper cleanup of client socket on exit.
    try:
        ##Step purpose: Receive data from client socket.
        ##BUFFER_SIZE limits how much data we read in one call.
        data = client_socket.recv(BUFFER_SIZE)
        
        ##Condition purpose: Check if data was received.
        ##Empty data indicates client disconnected without sending.
        if not data:
            logging.warning("Empty request received")
            return
        
        ##Step purpose: Decode and parse JSON request.
        ##UTF-8 is the standard encoding for JSON over sockets.
        request_str = data.decode('utf-8')
        logging.info(f"Received request: {request_str}")
        
        ##Error purpose: Handle JSON parsing errors gracefully.
        try:
            ##Action purpose: Parse JSON string into Python dictionary.
            request = json.loads(request_str)
        except json.JSONDecodeError as e:
            ##Error purpose: Return error response for malformed JSON.
            logging.error(f"Invalid JSON: {e}")
            response = {"status": "error", "message": "Invalid JSON format"}
            client_socket.sendall(json.dumps(response).encode('utf-8'))
            return
        
        ##Step purpose: Process the command and generate response.
        response = handle_command(request)
        
        ##Step purpose: Send response back to client.
        ##JSON encoding ensures consistent format, UTF-8 for transmission.
        response_str = json.dumps(response)
        client_socket.sendall(response_str.encode('utf-8'))
        
        ##Action purpose: Log response (truncated for large responses).
        logging.info(f"Sent response: {response_str[:100]}...")
    
    ##Error purpose: Handle any errors during client communication.
    except Exception as e:
        logging.error(f"Error handling client: {str(e)}")
    finally:
        ##Action purpose: Close the client socket connection.
        ##Finally block ensures cleanup even if exception occurred.
        client_socket.close()

##Function purpose: Clean up socket file on daemon shutdown.
##Unix Domain Sockets create a file on the filesystem. If not cleaned up properly,
##the file persists and prevents the daemon from binding to the same path on restart.
##This function is registered as a signal handler for SIGINT and SIGTERM.
##
##Parameters:
##  signum: Signal number (optional, for signal handler compatibility)
##  frame: Current stack frame (optional, for signal handler compatibility)
def cleanup_socket(signum=None, frame=None):
    ##Condition purpose: Remove socket file if it exists.
    ##os.path.exists check prevents errors if socket was never created.
    if os.path.exists(SOCKET_PATH):
        logging.info("Cleaning up socket file")
        ##Action purpose: Delete the socket file from filesystem.
        os.unlink(SOCKET_PATH)
    
    ##Action purpose: Exit the daemon gracefully.
    ##Exit code 0 indicates normal termination.
    sys.exit(0)

##Function purpose: Initialize and run the main socket server loop.
##This is the daemon's entry point that:
##  1. Parses command line arguments
##  2. Initializes logging
##  3. Verifies root privileges
##  4. Sets up signal handlers for graceful shutdown
##  5. Creates and binds the Unix Domain Socket
##  6. Enters the main accept/handle loop
##
##The daemon runs indefinitely until terminated by signal (SIGINT/SIGTERM)
##or an unrecoverable error occurs.
def main():
    ##Step purpose: Parse command line arguments.
    ##Allows configuration of the HCI device (e.g., ubt0hci, ubt1hci).
    global hci_device
    parser = argparse.ArgumentParser(description="FreeBSD Bluetooth TUI Daemon")
    parser.add_argument(
        "--device", 
        default=DEFAULT_HCI_DEVICE,
        help=f"Netgraph HCI node name (default: {DEFAULT_HCI_DEVICE})"
    )
    args = parser.parse_args()
    hci_device = args.device

    ##Step purpose: Set up logging before any other operations.
    ##This ensures all subsequent messages are properly logged.
    setup_logging()

    ##Step purpose: Log the startup configuration.
    logging.info(f"Starting bsd-bt-daemon using HCI device: {hci_device}")

    ##Step purpose: Verify root privileges before starting.
    ##Exit early if not root to avoid confusing errors later.
    check_root()
    
    ##Step purpose: Register signal handlers for graceful shutdown.
    ##SIGINT (Ctrl+C) and SIGTERM (kill) trigger cleanup_socket.
    signal.signal(signal.SIGINT, cleanup_socket)
    signal.signal(signal.SIGTERM, cleanup_socket)
    
    ##Step purpose: Remove existing socket file if present.
    ##This handles unclean shutdown where socket file was left behind.
    if os.path.exists(SOCKET_PATH):
        logging.warning(f"Removing existing socket: {SOCKET_PATH}")
        os.unlink(SOCKET_PATH)
    
    ##Step purpose: Create Unix Domain Socket.
    ##AF_UNIX = Unix domain, SOCK_STREAM = TCP-like reliable stream.
    server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    
    ##Error purpose: Ensure socket cleanup on any error.
    ##The try/finally guarantees cleanup even if an exception occurs.
    try:
        ##Action purpose: Bind socket to filesystem path.
        ##This creates /var/run/bt-tui.sock file.
        server_socket.bind(SOCKET_PATH)
        logging.info(f"Socket bound to {SOCKET_PATH}")
        
        ##Action purpose: Set socket file permissions to allow user access.
        ##0660 = owner read/write, group read/write, others none.
        ##This allows users in the same group as root to access the socket.
        os.chmod(SOCKET_PATH, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
        logging.info(f"Socket permissions set to 0660")
        
        ##Action purpose: Start listening for client connections.
        ##Backlog of 5 allows up to 5 pending connections in queue.
        server_socket.listen(5)
        logging.info("Daemon listening for connections...")
        
        ##Loop purpose: Accept and handle client connections continuously.
        ##This is the main event loop - runs until daemon is terminated.
        while True:
            ##Action purpose: Wait for and accept incoming client connection.
            ##This call blocks until a client connects.
            client_socket, _ = server_socket.accept()
            logging.info("Client connected")
            
            ##Action purpose: Process the client request.
            ##Each connection is handled synchronously (one at a time).
            handle_client_connection(client_socket)
    
    ##Error purpose: Handle any errors during socket operations.
    except Exception as e:
        logging.error(f"Server error: {str(e)}")
    finally:
        ##Action purpose: Clean up resources on exit.
        ##Close socket and remove socket file.
        server_socket.close()
        cleanup_socket()

##Condition purpose: Execute the main function if the script is run directly.
##This Python idiom allows the file to be imported as a module without
##automatically starting the daemon, while still running when executed directly.
if __name__ == "__main__":
    main()