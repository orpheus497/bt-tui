##Script function and purpose: Utility functions and shared constants for the bt-tui project.
##This module provides shared logic, constants, and helper functions used by both
##the bt-tui daemon (bt_daemon.py) and the TUI client (bt_tui.py).
##
##Purpose of Centralization:
##  - Ensures socket path and other constants are consistent across components
##  - Provides reusable utility functions to avoid code duplication
##  - Simplifies configuration changes by having single source of truth
##
##Usage:
##  from utils import SOCKET_PATH, BUFFER_SIZE, parse_ipc_message
##
##FreeBSD-Specific Notes:
##  - Socket path follows FreeBSD convention for runtime sockets (/var/run/)
##  - All functions are designed to work with FreeBSD's standard tools

import os
import json

##Step purpose: Define shared constants used by both client and server.
##This ensures the daemon and client connect to the same socket path.
##The path follows FreeBSD's convention: /var/run/ for runtime socket files.
##This directory is cleared on system reboot, ensuring clean state.
SOCKET_PATH = "/var/run/bt-tui.sock"

##Step purpose: Define buffer size for socket communication.
##4096 bytes is sufficient for JSON messages containing device lists.
BUFFER_SIZE = 4096


##Function purpose: Safely parse JSON data from the IPC socket.
##Provides robust JSON parsing with graceful error handling.
##Used by both daemon and client to decode incoming messages.
##
##Parameters:
##  message_str: Raw string received from socket, expected to be valid JSON
##
##Returns:
##  - Parsed dictionary if JSON is valid
##  - Error dictionary with status "error" if JSON is invalid
##
##Example:
##  data = parse_ipc_message('{"action": "scan"}')
##  # Returns: {"action": "scan"}
##
##  data = parse_ipc_message('invalid json')
##  # Returns: {"status": "error", "message": "Invalid JSON format"}
def parse_ipc_message(message_str):
    ##Error purpose: Handle potential JSON decoding errors.
    ##JSONDecodeError is raised when json.loads() receives malformed input.
    try:
        ##Action purpose: Parse JSON string into Python dictionary.
        return json.loads(message_str)
    except json.JSONDecodeError:
        ##Error purpose: Return standardized error response for invalid JSON.
        ##This allows callers to check status field for errors.
        return {"status": "error", "message": "Invalid JSON format"}


##Function purpose: Validate Bluetooth MAC address format.
##MAC addresses should be 6 hex octets separated by colons (XX:XX:XX:XX:XX:XX).
##
##Parameters:
##  mac_address: String to validate as MAC address
##
##Returns:
##  True if valid MAC format, False otherwise
##
##Example:
##  is_valid_mac("00:11:22:33:44:55")  # Returns: True
##  is_valid_mac("invalid")            # Returns: False
def is_valid_mac(mac_address):
    ##Condition purpose: Check for None or empty string.
    if not mac_address:
        return False
    
    ##Step purpose: Split MAC address by colons and validate structure.
    parts = mac_address.split(':')
    
    ##Condition purpose: MAC address must have exactly 6 octets.
    if len(parts) != 6:
        return False
    
    ##Loop purpose: Validate each octet is valid 2-digit hex.
    for part in parts:
        ##Condition purpose: Each octet must be exactly 2 characters.
        if len(part) != 2:
            return False
        
        ##Error purpose: Attempt hex conversion to validate characters.
        try:
            int(part, 16)
        except ValueError:
            ##Error purpose: Return False if non-hex characters found.
            return False
    
    ##Return purpose: All validation passed.
    return True


##Function purpose: Format device information for display.
##Creates a human-readable string from device dictionary.
##
##Parameters:
##  device: Dictionary with device info (mac, name, paired, connected)
##
##Returns:
##  Formatted string suitable for display
##
##Example:
##  format_device({"mac": "00:11:22:33:44:55", "name": "Headphones"})
##  # Returns: "Headphones (00:11:22:33:44:55)"
def format_device(device):
    ##Step purpose: Extract device properties with defaults.
    mac = device.get("mac", "Unknown")
    name = device.get("name", "Unknown")
    
    ##Step purpose: Build status indicators.
    status_parts = []
    if device.get("paired"):
        status_parts.append("Paired")
    if device.get("connected"):
        status_parts.append("Connected")
    
    ##Step purpose: Format final string.
    status_str = f" [{', '.join(status_parts)}]" if status_parts else ""
    
    return f"{name} ({mac}){status_str}"
