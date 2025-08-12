#!/usr/bin/env python3
"""Example usage of the PDF2HTML API."""

import asyncio
import httpx
import json
from pathlib import Path


async def convert_pdf_example():
    """Example of converting a PDF using the API."""
    
    # API endpoint (adjust if running on different host/port)
    api_url = "http://localhost:8000"
    
    # Example PDF URL (replace with a real PDF URL)
    pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    
    # Request payload
    payload = {
        "pdf_url": pdf_url,
        "model": "gpt-4o-mini",
        "dpi": 200,
        "max_tokens": 4000,
        "temperature": 0.0,
        "css_mode": "grid"
    }
    
    print(f"Converting PDF from: {pdf_url}")
    print(f"API endpoint: {api_url}/convert")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Convert PDF to HTML with JSON response
            print("\n1. Converting PDF to HTML (JSON response)...")
            response = await client.post(
                f"{api_url}/convert",
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Successfully converted {result['pages_processed']} pages")
                print(f"✓ Model used: {result['model_used']}")
                print(f"✓ CSS mode: {result['css_mode']}")
                print(f"✓ HTML preview: {result['html'][:200]}...")
                
                # Save the HTML to a file
                output_file = Path("output.html")
                output_file.write_text(result['html'], encoding='utf-8')
                print(f"✓ HTML saved to: {output_file.absolute()}")
                
            else:
                print(f"✗ Error: {response.status_code}")
                print(f"✗ Details: {response.text}")
                return
            
            # Convert PDF to HTML with direct HTML response
            print("\n2. Converting PDF to HTML (direct HTML response)...")
            response = await client.post(
                f"{api_url}/convert/html",
                json=payload
            )
            
            if response.status_code == 200:
                html_content = response.text
                print(f"✓ Successfully received HTML directly")
                print(f"✓ Content-Type: {response.headers.get('content-type')}")
                print(f"✓ HTML preview: {html_content[:200]}...")
                
                # Save the HTML to a file
                output_file = Path("output_direct.html")
                output_file.write_text(html_content, encoding='utf-8')
                print(f"✓ HTML saved to: {output_file.absolute()}")
                
            else:
                print(f"✗ Error: {response.status_code}")
                print(f"✗ Details: {response.text}")
    
    except httpx.ConnectError:
        print("✗ Error: Could not connect to the API server")
        print("Make sure the server is running with: python run_api.py")
    except httpx.TimeoutException:
        print("✗ Error: Request timed out")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")


async def test_api_endpoints():
    """Test basic API endpoints."""
    
    api_url = "http://localhost:8000"
    
    try:
        async with httpx.AsyncClient() as client:
            # Test root endpoint
            print("Testing root endpoint...")
            response = await client.get(f"{api_url}/")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ API: {data['message']} v{data['version']}")
            else:
                print(f"✗ Root endpoint failed: {response.status_code}")
            
            # Test health endpoint
            print("Testing health endpoint...")
            response = await client.get(f"{api_url}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Health: {data['status']}")
            else:
                print(f"✗ Health endpoint failed: {response.status_code}")
                
    except httpx.ConnectError:
        print("✗ Could not connect to API server")
        print("Make sure the server is running with: python run_api.py")


if __name__ == "__main__":
    print("PDF2HTML API Example Usage")
    print("=" * 50)
    
    # Test basic endpoints first
    asyncio.run(test_api_endpoints())
    
    print("\n" + "=" * 50)
    
    # Run the conversion example
    asyncio.run(convert_pdf_example()) 