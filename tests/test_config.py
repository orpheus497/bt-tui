##Script function and purpose: Unit tests for hcsecd.conf configuration management.
##This test module validates the update_hcsecd_conf() function in bt_daemon.py
##which is responsible for adding new Bluetooth device entries to FreeBSD's
##hcsecd configuration file for device pairing.
##
##Testing Strategy:
##  - Test adding a new device to existing config file
##  - Test handling of duplicate devices (already in config)
##  - Uses temporary files to avoid modifying system configuration
##
##FreeBSD Context:
##  /etc/bluetooth/hcsecd.conf is the configuration file for hcsecd (Bluetooth
##  Security Daemon). Each device entry contains:
##    - bdaddr: Bluetooth Device Address (MAC)
##    - name: Human-readable device name
##    - key: Link key for authenticated connections (nokey for new devices)
##    - pin: PIN code for legacy pairing
##
##Usage:
##  python -m pytest tests/test_config.py -v
##  python tests/test_config.py

import unittest
import tempfile
import os
import shutil
from src.bt_daemon import update_hcsecd_conf


##Class purpose: Test suite for the update_hcsecd_conf() function.
##Validates correct creation and updating of hcsecd.conf device entries.
class TestConfig(unittest.TestCase):
    
    ##Method purpose: Set up test fixtures before each test method.
    ##Creates a temporary directory and config file with initial content.
    def setUp(self):
        ##Step purpose: Create a temporary directory for test files.
        ##This isolates tests from the real /etc/bluetooth/ directory.
        self.test_dir = tempfile.mkdtemp()
        
        ##Step purpose: Define path to temporary config file.
        self.conf_path = os.path.join(self.test_dir, "hcsecd.conf")
        
        ##Step purpose: Write initial content with one existing device.
        ##This simulates a config file with pre-existing paired devices.
        with open(self.conf_path, "w") as f:
            f.write("# Default hcsecd.conf\ndevice {\n\tbdaddr 11:11:11:11:11:11;\n\tname \"Test\";\n}\n")

    ##Method purpose: Clean up test fixtures after each test method.
    ##Removes the temporary directory and all its contents.
    def tearDown(self):
        ##Action purpose: Remove temporary directory tree.
        shutil.rmtree(self.test_dir)

    ##Method purpose: Test adding a new device to hcsecd.conf.
    ##Verifies that a new device entry is correctly appended to the config.
    def test_add_new_device(self):
        ##Step purpose: Define test device parameters.
        mac = "00:11:22:33:44:55"
        pin = "1234"
        device_name = "NewDevice"
        
        ##Action purpose: Call function to add new device.
        updated = update_hcsecd_conf(self.conf_path, mac, pin, device_name)
        
        ##Assertion purpose: Verify function returned True (success).
        self.assertTrue(updated)
        
        ##Step purpose: Read updated config file.
        with open(self.conf_path, "r") as f:
            content = f.read()
        
        ##Assertion purpose: Verify MAC address was added to config.
        self.assertIn(f"bdaddr\t{mac};", content)
        
        ##Assertion purpose: Verify PIN was added to config.
        self.assertIn(f"pin\t\"{pin}\";", content)

    ##Method purpose: Test handling of device that already exists in config.
    ##Verifies that duplicate devices are not added and function returns False.
    def test_existing_device(self):
        ##Step purpose: Use MAC address that already exists in config.
        ##This MAC was added in setUp().
        mac = "11:11:11:11:11:11"
        
        ##Action purpose: Attempt to add existing device.
        updated = update_hcsecd_conf(self.conf_path, mac, "0000", "Ignored")
        
        ##Assertion purpose: Verify function returned False (device exists).
        ##This prevents duplicate entries in the config file.
        self.assertFalse(updated)


##Condition purpose: Run tests when script is executed directly.
##Allows running tests with: python tests/test_config.py
if __name__ == '__main__':
    unittest.main()
