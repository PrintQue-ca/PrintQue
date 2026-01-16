# PrintQue - 3D Printer Management System

PrintQue is a powerful and easy-to-use management system designed for 3D print farms. It provides centralized control, monitoring, and queue management for multiple 3D printers, helping you maximize efficiency and productivity.

## Features

- **Centralized Control**: Manage all your 3D printers from a single web interface
- **Queue Management**: Create, prioritize, and distribute print jobs automatically
- **Real-time Monitoring**: Track printer status, progress, and temperatures
- **Group Organization**: Organize printers into groups for specialized workloads
- **Automatic Ejection**: Configure custom end G-code for automated part removal
- **Statistics Tracking**: Monitor filament usage and printer performance
- **License Tiers**: Free, Standard, Professional, and Enterprise options to match your needs

## Getting Started

### System Requirements

- Windows 10 or newer
- 4GB RAM (8GB recommended)
- 500MB free disk space
- Network connectivity to your 3D printers

### Installation

1. Run the PrintQue installer (PrintQue_Setup.exe)
2. Follow the on-screen instructions
3. Enter your license key when prompted (or use the free tier)
4. Launch PrintQue from the desktop or start menu shortcut

### Accessing the Web Interface

PrintQue provides several ways to access its web interface:

- **Automatic Launch**: The web interface opens automatically when PrintQue starts
- **Desktop Shortcut**: Use the "PrintQue Web Interface" shortcut created during installation
- **Manual Access**: Open any web browser and navigate to http://localhost:5000

## Printer Setup

1. From the web interface, click "Add Printer"
2. Enter printer details:
   - Name: A descriptive name for the printer
   - IP Address: The IP address of the printer (must be on the same network)
   - API Key: The OctoPrint API key for the printer
   - Group: Assign the printer to a group (optional)

3. Click "Add" to connect the printer

## Creating Print Jobs

1. Click "New Print Job" on the main dashboard
2. Upload your G-code file
3. Select quantity and target printer group(s)
4. Enable ejection and configure end G-code if needed
5. Click "Create Job" to add it to the queue

PrintQue will automatically distribute jobs to available printers based on group assignments and printer availability.

## License Tiers

### FREE
- Up to 3 printers
- Basic printing and job queue

### STANDARD
- Up to 5 printers
- Advanced reporting
- Email notifications

### PROFESSIONAL
- Up to 15 printers
- Priority support
- API access

### ENTERPRISE
- Unlimited printers
- Custom branding
- Multi-tenant support

To upgrade your license, visit the License page in the application and enter your new license key.

## Troubleshooting

### Common Issues

- **Connection Issues**: Ensure printers are powered on and connected to the network
- **API Key Errors**: Verify your OctoPrint API key is correct
- **License Issues**: Check your license status on the License page

### Logs

Logs are stored in your user directory under PrintQueData/app.log and can help diagnose issues.

### Support

For assistance with PrintQue:
- Email: zhartley@hotmail.ca
- Visit: www.printque.ca
## Legal

PrintQue ©
All rights reserved.

This software is licensed, not sold. Usage is subject to the terms and conditions specified in the End User License Agreement.