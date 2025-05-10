#!/usr/bin/env python3
"""
Helsing Tactical Challenge - Main Entry Point

This is the main entry point for running the tactical simulation.
"""

import os
import sys
import logging
import argparse
import threading

from dotenv import load_dotenv

from simulator import Simulator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("main")

def main():
    """Main entry point for the simulation"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the Helsing Tactical Simulation :)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--delay", type=float, default=0.0, 
                       help="Delay before launching strike unit (seconds)")
    args = parser.parse_args()
    
    # Set log level based on debug flag
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Load environment variables
    load_dotenv()
    
    # Get server address and token
    server_address = os.getenv("SERVER_ADDRESS", "172.237.124.96:21234")
    
    # Use auth token from environment or generate a new one
    token = os.getenv("AUTH_TOKEN")
    if not token:
        token = os.urandom(40).hex()
        logger.info("Generated new auth token")
    
    logger.info(f"Using server: {server_address}")
    
    # Create and run simulator
    simulator = Simulator(server_address, token)
    simulator_thread = threading.Thread(target=simulator.run, kwargs={"strike_delay": args.delay}, daemon=True)
    simulator_thread.start()
    simulator.radar.run()
    return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user")
    except Exception as e:
        logger.error(f"Simulation failed with error: {e}")
        sys.exit(1)
