#!/usr/bin/env python3
"""
Helsing Tactical Challenge - Optimized Simulation Runner

This script runs the tactical simulation with optimized parameters for success.
"""

import os
import sys
import logging
import random
import argparse
from dotenv import load_dotenv

from simulation_controller import SimulationConfig, SimulationController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Create a logger for this module
logger = logging.getLogger("main")


def run_simulation(debug=False, strike_delay=5.0):
    """Run the simulation with the given parameters"""
    # Set log level based on debug flag
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    # Load environment variables
    load_dotenv()

    # Server address and port
    server_address = os.getenv("SERVER_ADDRESS", "172.237.124.96:21234")

    # Use auth token from environment or generate a new one
    token = "".join(os.urandom(40).hex())
    logger.info("Generated new auth token")

    logger.info(f"Using server: {server_address}")

    # Create simulation configuration
    config = SimulationConfig(server_address=server_address, auth_token=token)

    # Create and run simulation controller
    controller = SimulationController(config)
    controller.run(launch_strike_delay=strike_delay)


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the Helsing Tactical Simulation")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Delay before launching strike unit (seconds)",
    )
    args = parser.parse_args()

    try:
        run_simulation(debug=args.debug, strike_delay=args.delay)
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user")
    except Exception as e:
        logger.error(f"Simulation failed with error: {e}")
        sys.exit(1)
