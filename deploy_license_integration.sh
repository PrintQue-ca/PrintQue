#!/bin/bash
# Script to deploy license integration files to PrintQue

# Exit on error
set -e

# Set colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print header
echo -e "${GREEN}PrintQue License Integration Deployment${NC}"
echo "This script will update PrintQue with license integration files."
echo ""

# Check if PrintQue directory was provided as argument
if [ "$#" -ne 1 ]; then
    echo -e "${YELLOW}Usage: $0 /path/to/printque${NC}"
    echo "Please provide the path to your PrintQue installation."
    exit 1
fi

PRINTQUE_DIR=$1

# Check if the directory exists
if [ ! -d "$PRINTQUE_DIR" ]; then
    echo -e "${RED}Error: Directory $PRINTQUE_DIR does not exist.${NC}"
    exit 1
fi

# Check if the provided directory looks like a PrintQue installation
if [ ! -f "$PRINTQUE_DIR/app.py" ]; then
    echo -e "${YELLOW}Warning: The directory does not appear to be a PrintQue installation.${NC}"
    echo "Could not find app.py in $PRINTQUE_DIR"
    echo "Continue anyway? (y/n)"
    read -r CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        echo "Aborting."
        exit 1
    fi
fi

echo "Deploying license integration to $PRINTQUE_DIR"

# Create backup directory
BACKUP_DIR="$PRINTQUE_DIR/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
echo "Created backup directory: $BACKUP_DIR"

# Backup existing files
if [ -f "$PRINTQUE_DIR/license_validator.py" ]; then
    cp "$PRINTQUE_DIR/license_validator.py" "$BACKUP_DIR/"
    echo "Backed up license_validator.py"
fi

if [ -f "$PRINTQUE_DIR/license_routes.py" ]; then
    cp "$PRINTQUE_DIR/license_routes.py" "$BACKUP_DIR/"
    echo "Backed up license_routes.py"
fi

# Create templates directory if it doesn't exist
TEMPLATES_DIR="$PRINTQUE_DIR/templates"
if [ ! -d "$TEMPLATES_DIR" ]; then
    mkdir -p "$TEMPLATES_DIR"
    echo "Created templates directory"
fi

# Backup license.html if it exists
if [ -f "$TEMPLATES_DIR/license.html" ]; then
    cp "$TEMPLATES_DIR/license.html" "$BACKUP_DIR/"
    echo "Backed up license.html"
fi

# Copy updated files
echo "Copying updated license_validator.py..."
cp "updated-license-validator.py" "$PRINTQUE_DIR/license_validator.py"

echo "Copying updated license_routes.py..."
cp "updated-license-routes.py" "$PRINTQUE_DIR/license_routes.py"

echo "Copying updated license.html..."
cp "updated-license.html" "$TEMPLATES_DIR/license.html"

echo "Copying license integration test script..."
cp "license-integration-test.py" "$PRINTQUE_DIR/"
chmod +x "$PRINTQUE_DIR/license-integration-test.py"

# Check if routes registration is already in place
if grep -q "from license_routes import register_license_routes" "$PRINTQUE_DIR/routes.py"; then
    echo "License routes appear to be already registered in routes.py"
else
    echo -e "${YELLOW}Warning: Could not find license routes registration in routes.py${NC}"
    echo "You may need to manually update routes.py to include:"
    echo "from license_routes import register_license_routes"
    echo "and add register_license_routes(app, socketio) to the register_routes function"
fi

# Check if the license server URL environment variable is set
if [ -f "$PRINTQUE_DIR/.env" ]; then
    if grep -q "LICENSE_SERVER_URL" "$PRINTQUE_DIR/.env"; then
        echo "LICENSE_SERVER_URL is already set in .env file"
    else
        echo "Adding LICENSE_SERVER_URL to .env file"
        echo "LICENSE_SERVER_URL=http://localhost:5001" >> "$PRINTQUE_DIR/.env"
    fi
else
    echo "Creating .env file with LICENSE_SERVER_URL"
    echo "LICENSE_SERVER_URL=http://localhost:5001" > "$PRINTQUE_DIR/.env"
fi

# Create a default license.key file if it doesn't exist
if [ ! -f "$PRINTQUE_DIR/license.key" ]; then
    echo "Creating default license.key file"
    echo "FREE-0000-0000-0000" > "$PRINTQUE_DIR/license.key"
fi

echo -e "${GREEN}License integration deployed successfully!${NC}"
echo ""
echo "Next steps:"
echo "1. Make sure your license server is running"
echo "2. Test the integration with: python license-integration-test.py"
echo "3. Restart PrintQue to apply the changes"
echo "4. Navigate to http://your-printque-url/license to manage your license"
echo ""
echo "For troubleshooting, see the License Integration Guide."