"""
Simulator for Helsing tactical challenge

Manages the simulation and coordinates units.
"""

import logging
import time
import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.wrappers_pb2 import StringValue

import simulation_pb2
import simulation_pb2_grpc
from units import SensorUnit, StrikeUnit
from radar import Radar

# Configure module logger
logger = logging.getLogger("simulator")


class Simulator:
    """Main simulator that manages the units and overall simulation"""

    def __init__(self, server_address, auth_token):
        self.server_address = server_address
        self.auth_token = auth_token
        self.simulation_id = None
        self.base_position = None
        self.sensor_units = {}
        self.strike_unit = None
        self.radar = Radar(width=800, height=800)

    def start_simulation(self):
        """Start a new simulation and initialize units"""
        logger.info("Starting new simulation")

        try:
            # Create gRPC channel and stub
            with grpc.insecure_channel(self.server_address) as channel:
                stub = simulation_pb2_grpc.SimulationStub(channel)

                # Start simulation
                response = stub.Start(
                    Empty(), metadata=[("authorization", f"bearer {self.auth_token}")]
                )

                # Store simulation parameters
                self.simulation_id = response.id
                self.base_position = (response.base_pos.x, response.base_pos.y)

                # Log simulation parameters
                logger.info(f"Simulation started with ID: {self.simulation_id}")
                logger.info(
                    f"Base position: ({self.base_position[0]}, {self.base_position[1]})"
                )
                logger.info(f"Sensor units: {len(response.sensor_units)}")

                # Create sensor units
                for unit_id, pos in response.sensor_units.items():
                    start_pos = (pos.x, pos.y)
                    logger.info(f"  Unit {unit_id}: ({start_pos[0]}, {start_pos[1]})")

                    self.sensor_units[unit_id] = SensorUnit(
                        unit_id=unit_id,
                        simulation_id=self.simulation_id,
                        server_address=self.server_address,
                        auth_token=self.auth_token,
                        start_position=start_pos,
                        radar=self.radar,
                    )

                return True

        except Exception as e:
            logger.error(f"Failed to start simulation: {e}")
            return False

    def launch_strike_unit(self):
        """Launch the strike unit"""
        if not self.simulation_id:
            logger.error("Cannot launch strike unit: no active simulation")
            return False

        try:
            logger.info(f"Launching strike unit for simulation {self.simulation_id}")

            # Create gRPC channel and stub
            with grpc.insecure_channel(self.server_address) as channel:
                stub = simulation_pb2_grpc.SimulationStub(channel)

                # Launch strike unit
                request = StringValue(value=self.simulation_id)
                response = stub.LaunchStrikeUnit(
                    request, metadata=[("authorization", f"bearer {self.auth_token}")]
                )

                unit_id = response.id

                # Create strike unit
                self.strike_unit = StrikeUnit(
                    unit_id=unit_id,
                    simulation_id=self.simulation_id,
                    server_address=self.server_address,
                    auth_token=self.auth_token,
                    radar=self.radar,
                )

                return True

        except Exception as e:
            logger.error(f"Failed to launch strike unit: {e}")
            return False

    def get_simulation_status(self):
        """Get the current status of the simulation"""
        if not self.simulation_id:
            logger.error("Cannot get status: no active simulation")
            return None

        try:
            # Create gRPC channel and stub
            with grpc.insecure_channel(self.server_address) as channel:
                stub = simulation_pb2_grpc.SimulationStub(channel)

                # Get simulation status
                request = StringValue(value=self.simulation_id)
                response = stub.GetSimulationStatus(
                    request, metadata=[("authorization", f"bearer {self.auth_token}")]
                )

                # Log simulation status
                if hasattr(response, "status"):
                    status_map = {
                        0: "RUNNING",
                        1: "SUCCESS",
                        2: "TIMED_OUT",
                        3: "CANCELED",
                    }
                    status_str = status_map.get(response.status, str(response.status))
                    logger.info(f"Simulation status: {status_str}")
                    return response.status

                return None

        except Exception as e:
            logger.error(f"Failed to get simulation status: {e}")
            return None

    def run(self, strike_delay=5.0):
        """Run the full simulation"""
        # Start a new simulation
        if not self.start_simulation():
            return

        # Start all sensor units
        for sensor_unit in self.sensor_units.values():
            sensor_unit.start()

        # Wait before launching strike unit
        if strike_delay > 0:
            logger.info(
                f"Sensors activated. Waiting {strike_delay} seconds before launching strike unit..."
            )
            time.sleep(strike_delay)

        # Launch and start strike unit
        if self.launch_strike_unit():
            self.strike_unit.start()

        # Monitor simulation status
        try:
            logger.info("Simulation running, press Ctrl+C to exit...")
            while True:
                time.sleep(5)
                status = self.get_simulation_status()

                if status is not None and status != 0:  # Not RUNNING
                    status_map = {1: "SUCCESS", 2: "TIMED_OUT", 3: "CANCELED"}
                    status_str = status_map.get(status, str(status))
                    logger.info(f"Simulation ended with status: {status_str}")
                    break

        except KeyboardInterrupt:
            logger.info("Simulation interrupted by user")
        finally:
            # Stop all units
            for sensor_unit in self.sensor_units.values():
                sensor_unit.stop()

            if self.strike_unit:
                self.strike_unit.stop()
