##Script function and purpose: Unit tests for command-line argument parsing.
##This test module validates the command-line argument parsing functionality
##in bt_daemon.py, specifically testing the --device argument that allows
##users to specify a custom HCI device for Bluetooth operations.
##
##Testing Strategy:
##  - Test device name validation with valid and invalid formats
##  - Test that scan_devices properly accepts and uses the device parameter
##  - Focus on testable components without full main() execution
##
##FreeBSD Context:
##  FreeBSD uses netgraph HCI device names like ubt0hci, ubt1hci for USB
##  Bluetooth adapters. The naming convention is:
##    - ubt = USB Bluetooth device driver
##    - N = device number (0, 1, 2, etc.)
##    - hci = Host Controller Interface
##
##Usage:
##  python -m pytest tests/test_argparse.py -v
##  python tests/test_argparse.py

import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


##Class purpose: Test suite for command-line argument parsing and device handling.
##Validates that the HCI device parameter works correctly throughout the call chain.
class TestArgparse(unittest.TestCase):
    
    ##Method purpose: Test that scan_devices is called with the correct device.
    ##Verifies that the HCI device parameter is properly passed through.
    def test_scan_devices_receives_device(self):
        ##Step purpose: Import scan_devices after path is set.
        from bt_daemon import scan_devices
        
        ##Step purpose: Mock subprocess.run to avoid actual hccontrol execution.
        with patch('bt_daemon.subprocess.run') as mock_run:
            ##Step purpose: Configure mock to return successful result.
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Inquiry result, num_responses=1\n00:11:22:33:44:55"
            mock_run.return_value = mock_result
            
            ##Action purpose: Call scan_devices with custom device.
            custom_device = 'ubt1hci'
            result = scan_devices(custom_device)
            
            ##Assertion purpose: Verify subprocess.run was called with correct device.
            ##The device should be the 3rd argument (after 'hccontrol' and '-n').
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]  # Get the command list
            self.assertIn(custom_device, call_args)
            self.assertEqual(call_args[2], custom_device)
            
            ##Assertion purpose: Verify scan returned success with device data.
            self.assertEqual(result['status'], 'success')
            self.assertGreater(len(result['data']), 0)

    ##Method purpose: Test scan_devices with default device.
    ##Verifies that scan_devices works with the default ubt0hci device.
    def test_scan_devices_with_default_device(self):
        ##Step purpose: Import constants after path is set.
        from bt_daemon import scan_devices, DEFAULT_HCI_DEVICE
        
        with patch('bt_daemon.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "00:11:22:33:44:55"
            mock_run.return_value = mock_result
            
            ##Action purpose: Call scan_devices with default device.
            scan_devices(DEFAULT_HCI_DEVICE)
            
            ##Assertion purpose: Verify subprocess.run was called with default device.
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args[2], DEFAULT_HCI_DEVICE)

    ##Method purpose: Test handle_command passes device to scan_devices.
    ##Verifies that the device parameter flows through the command handler.
    def test_handle_command_passes_device(self):
        ##Step purpose: Import handle_command after path is set.
        from bt_daemon import handle_command
        
        ##Step purpose: Mock scan_devices to verify it receives the device.
        with patch('bt_daemon.scan_devices') as mock_scan:
            mock_scan.return_value = {"status": "success", "data": []}
            
            ##Action purpose: Call handle_command with scan action.
            custom_device = 'ubt2hci'
            command_data = {"action": "scan"}
            handle_command(command_data, custom_device)
            
            ##Assertion purpose: Verify scan_devices was called with correct device.
            mock_scan.assert_called_once_with(custom_device)

    ##Method purpose: Test device name validation for valid format.
    ##Verifies that valid device names (ubt0hci, ubt1hci, etc.) pass validation.
    def test_device_validation_valid(self):
        ##Step purpose: Import the pattern constant from bt_daemon.
        from bt_daemon import HCI_DEVICE_PATTERN
        import re
        
        ##Step purpose: Define valid device names following ubtNhci pattern.
        valid_devices = ['ubt0hci', 'ubt1hci', 'ubt9hci', 'ubt10hci', 'ubt123hci']
        
        ##Loop purpose: Test each valid device name.
        for device in valid_devices:
            ##Assertion purpose: Verify device matches expected pattern.
            ##Pattern should match ubt followed by digits followed by hci.
            self.assertTrue(
                re.match(HCI_DEVICE_PATTERN, device),
                f"Device '{device}' should match pattern"
            )

    ##Method purpose: Test device name validation for invalid format.
    ##Verifies that invalid device names don't match the expected pattern.
    def test_device_validation_invalid(self):
        ##Step purpose: Import the pattern constant from bt_daemon.
        from bt_daemon import HCI_DEVICE_PATTERN
        import re
        
        ##Step purpose: Define invalid device names that don't follow pattern.
        invalid_devices = ['ubt', 'hci0', 'bt0hci', 'ubt0', 'custom_device', 'UBT0HCI', 'ubt0hci ']
        
        ##Loop purpose: Test each invalid device name.
        for device in invalid_devices:
            ##Assertion purpose: Verify device doesn't match expected pattern.
            ##These should be rejected (or at least flagged with warning).
            self.assertFalse(
                re.match(HCI_DEVICE_PATTERN, device),
                f"Device '{device}' should not match pattern"
            )

    ##Method purpose: Test argparse accepts --device argument.
    ##Verifies that ArgumentParser correctly handles the --device flag.
    def test_argparse_accepts_device_flag(self):
        ##Step purpose: Test ArgumentParser configuration using factory function.
        from bt_daemon import create_arg_parser, DEFAULT_HCI_DEVICE
        
        ##Step purpose: Create parser using the factory function from bt_daemon.
        ##This ensures tests exercise the real parser implementation.
        parser = create_arg_parser()
        
        ##Test purpose: Parse args with no flags (should use default).
        args = parser.parse_args([])
        self.assertEqual(args.device, DEFAULT_HCI_DEVICE)
        
        ##Test purpose: Parse args with --device flag.
        args = parser.parse_args(['--device', 'ubt1hci'])
        self.assertEqual(args.device, 'ubt1hci')
        
        ##Test purpose: Parse args with --device and custom value.
        args = parser.parse_args(['--device', 'custom_hci'])
        self.assertEqual(args.device, 'custom_hci')


##Condition purpose: Run tests when script is executed directly.
##Allows running tests with: python tests/test_argparse.py
if __name__ == '__main__':
    unittest.main()

