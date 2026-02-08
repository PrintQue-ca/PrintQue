#!/bin/bash

# PrintQue Installation Script for macOS
echo "==== PrintQue Installation Script ===="
echo "This script will install Docker, set up PrintQue, and create a launch agent."

# Check if script is run with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

# Check for Homebrew and install if not found
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    echo "Homebrew installed successfully!"
else
    echo "Homebrew already installed. Skipping."
fi

# Install Docker if not installed
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    brew install --cask docker
    echo "Docker installed successfully!"
    echo "Please open Docker Desktop and follow the setup instructions."
    echo "Press Enter when Docker is running..."
    read
else
    echo "Docker already installed. Skipping."
fi

# Check if Docker is running
echo "Checking if Docker is running..."
if ! docker info &> /dev/null; then
    echo "Docker is not running. Please start Docker Desktop manually."
    echo "Press Enter when Docker is running..."
    read
    
    # Check again
    if ! docker info &> /dev/null; then
        echo "Docker is still not running. Please start Docker Desktop and try again."
        exit 1
    fi
fi

# Create PrintQue directory
mkdir -p /Applications/PrintQue
cd /Applications/PrintQue

# Download PrintQue files
echo "Downloading PrintQue files..."
curl -L "https://download.printque.com/latest/printque-macos.zip" -o printque.zip
unzip -o printque.zip
rm printque.zip

# Setup environment
echo "Setting up environment..."
if [ ! -f .env ]; then
    # Generate random secret key
    SECRET_KEY=$(openssl rand -hex 24)
    echo "SECRET_KEY=$SECRET_KEY" > .env
    
    # Generate random encryption key
    ENCRYPTION_KEY=$(openssl rand -hex 16)
    echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" >> .env
    
    # Ask for license key
    read -p "Enter your license key (leave empty for free tier): " LICENSE_KEY
    if [ ! -z "$LICENSE_KEY" ]; then
        echo "LICENSE_KEY=$LICENSE_KEY" >> .env
    fi
    
    # Set environment variable for containerized env
    echo "CONTAINERIZED=true" >> .env
fi

# Create launch agent
echo "Creating LaunchAgent for auto-start..."
cat > /Library/LaunchAgents/com.printque.app.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.printque.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/docker-compose</string>
        <string>-f</string>
        <string>/Applications/PrintQue/docker-compose.yml</string>
        <string>up</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/Applications/PrintQue</string>
    <key>StandardErrorPath</key>
    <string>/Applications/PrintQue/error.log</string>
    <key>StandardOutPath</key>
    <string>/Applications/PrintQue/output.log</string>
</dict>
</plist>
EOF

launchctl load -w /Library/LaunchAgents/com.printque.app.plist

# Start PrintQue
echo "Starting PrintQue..."
cd /Applications/PrintQue
docker-compose up -d

# Create Applications shortcut
echo "Creating application shortcut..."
cat > /Applications/PrintQue.command << EOF
#!/bin/bash
open http://localhost:8000
EOF
chmod +x /Applications/PrintQue.command

echo
echo "==== Installation Complete ===="
echo "PrintQue is now running at http://localhost:8000"
echo "Default admin credentials: admin / printque"
echo "Please change these credentials on first login!"
echo
echo "A shortcut has been created in your Applications folder."
echo "PrintQue will automatically start when you log in."
