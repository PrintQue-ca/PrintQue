# PrintQue - 3D Printer Management System

PrintQue is a powerful and easy-to-use management system designed for 3D print farms. It provides centralized control, monitoring, and queue management for multiple 3D printers, helping you maximize efficiency and productivity.

## Quick Start

### Backend (API Server)

```bash
# Install
cd api
python -m venv .venv
# Windows (Command Prompt):
.venv\Scripts\activate
# Windows (Git Bash) / macOS / Linux:
source .venv/Scripts/activate  # Git Bash
source .venv/bin/activate      # macOS/Linux
pip install -r requirements.txt

# Start
python app.py
```

The API server runs on **http://localhost:5000**

### Frontend (React App)

```bash
# Install
cd app
npm install

# Start
npm run dev
```

The frontend runs on **http://localhost:3000**

## Tech Stack

### Frontend
- **React 19** - Modern UI framework
- **TypeScript** - Type-safe development
- **Vite 7** - Fast build tooling and dev server
- **TanStack Router** - Type-safe file-based routing
- **TanStack Query** - Data fetching and caching
- **TanStack Table** - Headless table component
- **Tailwind CSS 4** - Utility-first styling
- **Radix UI** - Accessible UI primitives (Dialog, Dropdown, Select, Tabs, etc.)
- **Lucide React** - Icon library
- **Socket.IO Client** - Real-time WebSocket communication
- **React Hook Form + Zod** - Form handling and validation
- **Sonner** - Toast notifications

### Backend
- **Python 3** - Backend runtime
- **Flask** - Web framework
- **Flask-SocketIO** - Real-time WebSocket support
- **Flask-CORS** - Cross-origin resource sharing
- **Eventlet** - Async/concurrent networking
- **aiohttp/aiofiles** - Async HTTP and file operations
- **Paho MQTT** - Bambu printer communication
- **Cryptography** - License validation and security

### Printer Support
- **OctoPrint** - API integration for OctoPrint-compatible printers
- **Bambu Lab** - Native support via MQTT and FTP protocols

## Features

- **Centralized Control**: Manage all your 3D printers from a single web interface
- **Queue Management**: Create, prioritize, and distribute print jobs automatically
- **Real-time Monitoring**: Track printer status, progress, and temperatures via WebSocket
- **Group Organization**: Organize printers into groups for specialized workloads
- **Automatic Ejection**: Configure custom end G-code for automated part removal
- **Statistics Tracking**: Monitor filament usage and printer performance
- **Dark/Light Theme**: Toggle between themes for comfortable viewing
- **License Tiers**: Free, Standard, Professional, and Enterprise options

## Getting Started

### Prerequisites

- **Node.js 18+** (for frontend)
- **Python 3.10+** (for backend)
- **pip** (Python package manager)
- Network connectivity to your 3D printers

### Installation

#### 1. Clone the Repository

```bash
git clone <repository-url>
cd Printque
```

#### 2. Backend Setup

```bash
# Navigate to the API directory
cd api

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 3. Frontend Setup

```bash
# Navigate to the app directory
cd app

# Install dependencies
npm install
```

### Running the Application

You need to run both the backend and frontend servers:

#### Start the Backend (API Server)

```bash
cd api

# Activate virtual environment if not already active
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Run the server
python app.py
```

The API server will start on **http://localhost:5000**

#### Start the Frontend (Dev Server)

In a separate terminal:

```bash
cd app

# Start the development server
npm run dev
```

The frontend will start on **http://localhost:3000**

### Production Build

To build the frontend for production:

```bash
cd app
npm run build
```

The built files will be in the `app/dist` directory.

## Project Structure

```
Printque/
├── api/                    # Python backend
│   ├── app.py              # Main Flask application
│   ├── requirements.txt    # Python dependencies
│   ├── routes/             # API route handlers
│   │   ├── history.py      # Print history endpoints
│   │   ├── license.py      # License management
│   │   ├── orders.py       # Order/job management
│   │   ├── printers.py     # Printer management
│   │   ├── support.py      # Support endpoints
│   │   └── system.py       # System information
│   ├── services/           # Business logic
│   │   ├── bambu_handler.py    # Bambu printer integration
│   │   ├── bambu_ftp.py        # Bambu FTP protocol
│   │   ├── printer_manager.py  # Printer orchestration
│   │   └── state.py            # Application state
│   ├── utils/              # Utility modules
│   └── templates/          # Legacy HTML templates
│
├── app/                    # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   │   ├── layout/     # Layout components
│   │   │   ├── orders/     # Order-related components
│   │   │   ├── printers/   # Printer-related components
│   │   │   └── ui/         # Reusable UI components (shadcn/ui)
│   │   ├── hooks/          # Custom React hooks
│   │   ├── lib/            # Utilities and API client
│   │   ├── routes/         # TanStack Router pages
│   │   └── types/          # TypeScript type definitions
│   ├── package.json        # Node dependencies
│   ├── vite.config.ts      # Vite configuration
│   └── tsconfig.json       # TypeScript configuration
│
└── README.md
```

## Printer Setup

1. From the web interface, click "Add Printer"
2. Enter printer details:
   - **Name**: A descriptive name for the printer
   - **IP Address**: The IP address of the printer
   - **API Key**: The OctoPrint API key (for OctoPrint printers)
   - **Access Code**: The LAN access code (for Bambu printers)
   - **Group**: Assign the printer to a group (optional)
3. Click "Add" to connect the printer

## Creating Print Jobs

1. Click "New Print Job" on the main dashboard
2. Upload your G-code file
3. Select quantity and target printer group(s)
4. Enable ejection and configure end G-code if needed
5. Click "Create Job" to add it to the queue

PrintQue will automatically distribute jobs to available printers based on group assignments and availability.

## License Tiers

| Tier | Printers | Features |
|------|----------|----------|
| **Free** | Up to 3 | Basic printing and job queue |
| **Standard** | Up to 5 | Advanced reporting, email notifications |
| **Professional** | Up to 15 | Priority support, API access |
| **Enterprise** | Unlimited | Custom branding, multi-tenant support |

To upgrade your license, visit the License page in the application.

## Troubleshooting

### Common Issues

- **Connection Issues**: Ensure printers are powered on and connected to the network
- **API Key Errors**: Verify your OctoPrint API key is correct
- **Bambu Connection**: Check the LAN access code and ensure MQTT is enabled
- **License Issues**: Check your license status on the License page

### Logs

Logs are stored in your user directory:
- **Location**: `~/PrintQueData/app.log`

### Support

For assistance with PrintQue:
- **Email**: zhartley@hotmail.ca
- **Website**: www.printque.ca

## Development

### Running Tests

```bash
cd app
npm run test
```

### Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server on port 3000 |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run test` | Run tests with Vitest |

## Legal

PrintQue © All rights reserved.

This software is licensed, not sold. Usage is subject to the terms and conditions specified in the End User License Agreement.
