#!/usr/bin/env python3
"""
Test script to verify parallel processing is working correctly.

This script tests whether multiple pages are being processed in parallel
by monitoring the timing and log output.
"""

import asyncio
import httpx
import time
import json
from pathlib import Path

async def test_parallel_processing():
    """Test if parallel processing is working."""
    
    API_URL = "http://localhost:8000"
    # Use a multi-page PDF for testing
    TEST_PDF_URL = "https://arxiv.org/pdf/2303.08774.pdf"  # Should have multiple pages
    
    print("🧪 Testing Parallel Processing")
    print("=" * 40)
    print(f"API URL: {API_URL}")
    print(f"Test PDF: {TEST_PDF_URL}")
    print()
    
    # Check if API is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/health")
            if response.status_code != 200:
                print("❌ API not responding. Make sure it's running.")
                return False
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        return False
    
    print("✅ API is running")
    print()
    
    # Test with different parallel worker configurations
    test_configs = [
        {"max_parallel_workers": 1, "name": "Sequential (1 worker)"},
        {"max_parallel_workers": 3, "name": "Parallel (3 workers)"},
        {"max_parallel_workers": 5, "name": "High Parallel (5 workers)"},
    ]
    
    results = []
    
    for config in test_configs:
        print(f"\n🔄 Testing: {config['name']}")
        print(f"   Workers: {config['max_parallel_workers']}")
        
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{API_URL}/convert",
                    json={
                        "pdf_url": TEST_PDF_URL,
                        "model": "gpt-4o-mini",
                        "dpi": 150,
                        "max_tokens": 1500,
                        "temperature": 0.0,
                        "css_mode": "grid",
                        "max_parallel_workers": config['max_parallel_workers']
                    }
                )
                
                total_time = time.time() - start_time
                
                if response.status_code == 200:
                    result = response.json()
                    
                    test_result = {
                        "config": config['name'],
                        "workers": config['max_parallel_workers'],
                        "success": True,
                        "total_time": total_time,
                        "pages_processed": result['pages_processed'],
                        "html_length": len(result['html'])
                    }
                    
                    results.append(test_result)
                    
                    print(f"   ✅ Completed in {total_time:.2f}s")
                    print(f"   📄 Pages: {result['pages_processed']}")
                    print(f"   📏 HTML: {len(result['html']):,} chars")
                    
                    # Calculate time per page
                    if result['pages_processed'] > 0:
                        time_per_page = total_time / result['pages_processed']
                        print(f"   ⏱️  Time per page: {time_per_page:.2f}s")
                    
                else:
                    print(f"   ❌ Failed: HTTP {response.status_code}")
                    print(f"   Error: {response.text}")
                    
        except Exception as e:
            total_time = time.time() - start_time
            print(f"   ❌ Failed after {total_time:.2f}s: {e}")
    
    # Analyze results
    print("\n📊 Parallel Processing Analysis")
    print("=" * 40)
    
    if len(results) >= 2:
        # Compare sequential vs parallel
        sequential = next((r for r in results if r['workers'] == 1), None)
        parallel = next((r for r in results if r['workers'] > 1), None)
        
        if sequential and parallel:
            speedup = sequential['total_time'] / parallel['total_time']
            improvement = ((sequential['total_time'] - parallel['total_time']) / sequential['total_time']) * 100
            
            print(f"Sequential (1 worker): {sequential['total_time']:.2f}s")
            print(f"Parallel ({parallel['workers']} workers): {parallel['total_time']:.2f}s")
            print(f"Speedup: {speedup:.1f}x faster")
            print(f"Improvement: {improvement:.1f}%")
            
            if speedup > 1.5:
                print("✅ Parallel processing is working well!")
            elif speedup > 1.1:
                print("⚠️ Parallel processing is working, but improvement is minimal")
            else:
                print("❌ Parallel processing may not be working correctly")
    
    # Check logs for parallel processing indicators
    print("\n📋 Checking Logs for Parallel Processing")
    print("-" * 40)
    
    log_file = Path("pdf2html_api.log")
    if log_file.exists():
        with open(log_file, 'r') as f:
            log_content = f.read()
            
        # Look for parallel processing indicators
        parallel_indicators = [
            "Starting parallel processing",
            "Processing page",
            "Page.*completed in"
        ]
        
        import re
        for indicator in parallel_indicators:
            matches = re.findall(indicator, log_content)
            if matches:
                print(f"✅ Found {len(matches)} instances of: {indicator}")
            else:
                print(f"❌ Not found: {indicator}")
        
        # Check for overlapping timestamps (indicates parallel processing)
        import re
        page_completion_times = re.findall(r'Page (\d+) completed in ([\d.]+)s', log_content)
        
        if len(page_completion_times) > 1:
            print(f"✅ Found {len(page_completion_times)} page completions")
            
            # Check if pages completed around the same time (indicating parallel processing)
            completion_times = [float(time) for _, time in page_completion_times]
            time_range = max(completion_times) - min(completion_times)
            
            if time_range < 5:  # If pages completed within 5 seconds of each other
                print("✅ Pages completed close together - parallel processing likely working")
            else:
                print("⚠️ Pages completed far apart - may be sequential processing")
        else:
            print("❌ Not enough page completion data to analyze")
    else:
        print("❌ Log file not found")
    
    return True

async def test_single_vs_multi_page():
    """Test single page vs multi-page processing."""
    
    API_URL = "http://localhost:8000"
    
    print("\n🔍 Single vs Multi-Page Processing Test")
    print("=" * 50)
    
    # Test with a single-page PDF and multi-page PDF
    test_pdfs = [
        {"url": "https://arxiv.org/pdf/2303.08774.pdf", "name": "Multi-page PDF"},
        # You can add a single-page PDF here for comparison
    ]
    
    for pdf in test_pdfs:
        print(f"\n📄 Testing: {pdf['name']}")
        
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{API_URL}/convert",
                    json={
                        "pdf_url": pdf['url'],
                        "model": "gpt-4o-mini",
                        "dpi": 150,
                        "max_tokens": 1500,
                        "temperature": 0.0,
                        "css_mode": "grid",
                        "max_parallel_workers": 3
                    }
                )
                
                total_time = time.time() - start_time
                
                if response.status_code == 200:
                    result = response.json()
                    time_per_page = total_time / result['pages_processed'] if result['pages_processed'] > 0 else 0
                    
                    print(f"   Total time: {total_time:.2f}s")
                    print(f"   Pages: {result['pages_processed']}")
                    print(f"   Time per page: {time_per_page:.2f}s")
                    
                    if result['pages_processed'] > 1:
                        expected_sequential = time_per_page * result['pages_processed']
                        if total_time < expected_sequential * 0.8:  # 20% improvement threshold
                            print("   ✅ Parallel processing likely working (faster than expected)")
                        else:
                            print("   ⚠️ May be sequential processing (slower than expected)")
                else:
                    print(f"   ❌ Failed: {response.status_code}")
                    
        except Exception as e:
            print(f"   ❌ Error: {e}")

def main():
    """Main function."""
    print("🚀 Parallel Processing Test")
    print("=" * 30)
    
    # Run tests
    asyncio.run(test_parallel_processing())
    asyncio.run(test_single_vs_multi_page())
    
    print("\n📝 Next Steps:")
    print("1. Check the logs for 'Starting parallel processing' messages")
    print("2. Look for overlapping page processing timestamps")
    print("3. Compare single vs multi-page processing times")
    print("4. Monitor CPU usage during processing")

if __name__ == "__main__":
    main()

