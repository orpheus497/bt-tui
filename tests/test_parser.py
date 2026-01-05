##Script function and purpose: Unit tests for hccontrol output parsing.
##This test module validates the parse_inquiry_output() function in bt_daemon.py
##which is responsible for extracting Bluetooth device information from the
##output of FreeBSD's hccontrol inquiry command.
##
##Testing Strategy:
##  - Test simple output format (just MAC addresses)
##  - Test verbose output format (BD_ADDR labels with metadata)
##  - Test garbage/invalid input handling
##  - Verify MAC address extraction accuracy
##
##FreeBSD Context:
##  hccontrol inquiry output format varies by Bluetooth adapter and firmware.
##  Common formats include:
##    - Plain MAC: "00:11:22:33:44:55"
##    - Labeled: "BD_ADDR: 00:11:22:33:44:55"
##    - Numbered results: "Inquiry result #0" followed by device details
##
##Usage:
##  python -m pytest tests/test_parser.py -v
##  python tests/test_parser.py

import unittest
from src.bt_daemon import parse_inquiry_output


##Class purpose: Test suite for the parse_inquiry_output() function.
##Validates correct extraction of MAC addresses from various hccontrol output formats.
class TestParser(unittest.TestCase):
    
    ##Method purpose: Test parsing of simple output with standalone MAC address.
    ##This format occurs when hccontrol outputs just the MAC on its own line.
    def test_parse_simple_output(self):
        ##Step purpose: Create sample output where MAC is standalone on a line.
        ##This mimics minimal hccontrol output format.
        sample_output = """
        Inquiry result, num_responses=1
        00:11:22:33:44:55
        """
        
        ##Action purpose: Parse the sample output.
        devices = parse_inquiry_output(sample_output)
        
        ##Assertion purpose: Verify exactly one device was found.
        self.assertEqual(len(devices), 1)
        
        ##Assertion purpose: Verify correct MAC address extracted.
        self.assertEqual(devices[0]['mac'], "00:11:22:33:44:55")

    ##Method purpose: Test parsing of verbose output with BD_ADDR labels.
    ##This format is common with many Bluetooth adapters and includes metadata.
    def test_parse_verbose_output(self):
        ##Step purpose: Create sample output with labeled BD_ADDR format.
        ##Includes multiple devices with additional metadata lines.
        sample_output = """
        Inquiry result, num_responses=2
        Inquiry result #0
            BD_ADDR: 11:22:33:44:55:66
            Page Scan Rep. Mode: 0x1
        Inquiry result #1
            BD_ADDR: AA:BB:CC:DD:EE:FF
            Page Scan Rep. Mode: 0x1
        """
        
        ##Action purpose: Parse the sample output.
        devices = parse_inquiry_output(sample_output)
        
        ##Assertion purpose: Verify exactly two devices were found.
        self.assertEqual(len(devices), 2)
        
        ##Assertion purpose: Verify first device MAC.
        self.assertEqual(devices[0]['mac'], "11:22:33:44:55:66")
        
        ##Assertion purpose: Verify second device MAC.
        self.assertEqual(devices[1]['mac'], "AA:BB:CC:DD:EE:FF")

    ##Method purpose: Test that garbage input returns empty device list.
    ##Ensures parser doesn't crash or return false positives on invalid input.
    def test_parse_garbage(self):
        ##Step purpose: Create sample output with no valid MAC addresses.
        ##Includes lines that might superficially resemble MAC format.
        sample_output = """
        Nothing to see here
        Just some random text
        123:456
        """
        
        ##Action purpose: Parse the garbage output.
        devices = parse_inquiry_output(sample_output)
        
        ##Assertion purpose: Verify no devices were found (graceful handling).
        self.assertEqual(len(devices), 0)


##Condition purpose: Run tests when script is executed directly.
##Allows running tests with: python tests/test_parser.py
if __name__ == '__main__':
    unittest.main()