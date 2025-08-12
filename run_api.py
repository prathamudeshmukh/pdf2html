#!/usr/bin/env python3
"""Simple script to run the PDF2HTML API server."""

import os
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    print(f"Starting PDF2HTML API server on {host}:{port}")
    print(f"API documentation available at: http://{host}:{port}/docs")
    print(f"Health check available at: http://{host}:{port}/health")
    
    # Run the server
    uvicorn.run(
        "src.pdf2html_api.main:app",
        host=host,
        port=port,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    ) 