# Beauty Salon Assistant

This project provides an intelligent assistant and appointment management system designed for beauty salons. It leverages an agent-based architecture to handle various tasks such as appointment scheduling, customer management, marketing suggestions, and service availability checks. The system includes a web interface for easy interaction and management.

## Features

*   **Appointment Management:** Schedule, check availability, and cancel appointments.
*   **Customer Management:** Register new customers, retrieve customer information, and view past appointments.
*   **Service Catalog:** List available services and their durations.
*   **Expert Management:** List available experts and their specialties.
*   **Complementary Service Suggestions:** Suggest additional services based on selected primary services.
*   **Campaign Management:** Check for applicable campaigns for customers (e.g., first-time customer, loyalty programs).
*   **Modular Agent System:** Utilizes specialized agents for different functionalities (Appointment, Customer, Marketing, Orchestrator).
*   **Web Interface:** A user-friendly web application for salon staff to manage operations.

## Technologies Used

*   **Backend:** Python, FastAPI, FastMCP (for agent communication)
*   **Database:** PostgreSQL
*   **Web Server:** Uvicorn
*   **Containerization:** Docker, Docker Compose
*   **Frontend:** HTML, CSS, JavaScript (for the web interface)

## Project Structure

```
Beauty-Salon-Assistant/
├── .gitignore
├── docker-compose.yml          # Docker Compose configuration for services
├── README.md                   # Project README file
├── backend/                    # Backend application code
│   ├── agents/                 # Modular agents for specific tasks
│   │   ├── appointment_agent.py
│   │   ├── customer_agent.py
│   │   ├── marketing_agent.py
│   │   └── orchestrator_agent.py
│   ├── config.py               # Application configuration
│   ├── database.py             # Database connection and utilities
│   ├── main.py                 # Main FastAPI application entry point
│   ├── mcp_server.py           # FastMCP server for agent communication
│   ├── models.py               # Database models (Pydantic/SQLAlchemy)
│   ├── orchestrator.py         # Orchestrates agent interactions
│   ├── repository.py           # Data access layer
│   ├── requirements.txt        # Python dependencies
│   ├── static/                 # Static files (CSS, JS) for the web interface
│   └── templates/              # HTML templates for the web interface
├── docs/                       # Documentation and miscellaneous files
│   └── test_konusma.md         # (Optional) Test conversation logs or notes
└── scripts/                    # Utility and startup scripts
    ├── install_ffmpeg.py       # Script for FFmpeg installation (if needed)
    ├── start_mcp_server.bat    # Windows batch script to start the MCP server
    └── start_web_server.bat    # Windows batch script to start the web server
```

## Setup and Installation

Follow these steps to get the project up and running on your local machine.

### Prerequisites

*   [Docker Desktop](https://www.docker.com/products/docker-desktop) (includes Docker Engine and Docker Compose)
*   [Python 3.8+](https://www.python.org/downloads/)

### 1. Clone the Repository

```bash
git clone https://github.com/HamdiOzkurt/-Beauty-Salon-Assistant.git
cd Beauty-Salon-Assistant
```

### 2. Set up the Database (PostgreSQL with Docker Compose)

Navigate to the project root directory and start the database service:

```bash
docker-compose up -d db
```
This will start a PostgreSQL container. You can verify it's running with `docker-compose ps`.

### 3. Create a Python Virtual Environment and Install Dependencies

It's recommended to use a virtual environment to manage project dependencies.

```bash
python -m venv venv
.\venv\Scripts\activate  # On Windows
# source venv/bin/activate # On macOS/Linux

pip install -r backend/requirements.txt
```

### 4. Configure Environment Variables

Copy the example environment file and fill in your details.

```bash
copy backend\.env.example backend\.env
# On macOS/Linux: cp backend/.env.example backend/.env
```
Edit `backend/.env` to configure your database connection and any other necessary settings.

### 5. Run the Servers

Once the database is running and dependencies are installed, you can start the application servers.

#### Start the MCP Server

This server handles the agent communication and tool execution.

```bash
.\scripts\start_mcp_server.bat
```

#### Start the Web Server

This server hosts the FastAPI application and the web interface.

```bash
.\scripts\start_web_server.bat
```

The application should now be accessible at `http://localhost:8000`.

## Usage

Access the web interface at `http://localhost:8000` to interact with the Beauty Salon Assistant. The FastAPI documentation (Swagger UI) for the backend API can be found at `http://localhost:8000/docs`.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

[Specify your license here, e.g., MIT License]