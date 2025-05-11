"""
Units for Helsing tactical simulation

Contains the SensorUnit and StrikeUnit implementations.
"""

import utils
import logging
import threading
import queue
import grpc
import enum
from google.protobuf.wrappers_pb2 import StringValue
from google.protobuf import any_pb2
import time

import simulation_pb2
import simulation_pb2_grpc
from navigation import UnitNavigator

# Configure module logger
logger = logging.getLogger("units")


class UnitState(enum.Enum):
    """Enum for unit states"""

    PATROL = 1  # Unit is patrolling assigned area
    ATTACK = 2  # Unit is following target


class SensorUnit:
    """A sensor unit that detects targets and broadcasts information"""

    def __init__(
        self,
        unit_id,
        simulation_id,
        server_address,
        auth_token,
        start_position=None,
        radar=None,
    ):
        self.unit_id = unit_id
        self.simulation_id = simulation_id
        self.server_address = server_address
        self.auth_token = auth_token
        self.position = start_position or (0.0, 0.0)
        self.logger = logging.getLogger(f"sensor-{unit_id}")
        self.response_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.navigator = UnitNavigator()
        self.radar = radar

        # State management
        self.state = UnitState.PATROL
        self.target_position = None

        # Set patrol position based on unit ID
        patrol_positions = [(50, 50), (-50, 50), (-50, -50), (50, -50)]
        idx = int(unit_id) - 1
        self.initial_patrol_position = patrol_positions[idx]
        self.subpatrol_positions = [(10, 10), (-10, 10), (-10, -10), (10, -10)]
        self.subpatrol_idx = 0
        self.navigator.set_target(self.patrol_position)

    @property
    def patrol_position(self):
        return (
            self.initial_patrol_position[0]
            + self.subpatrol_positions[self.subpatrol_idx][0],
            self.initial_patrol_position[1]
            + self.subpatrol_positions[self.subpatrol_idx][1],
        )

    def start(self):
        """Start the sensor unit in a background thread"""
        if self.thread is None:
            self.running = True
            self.thread = threading.Thread(target=self._control_loop, daemon=True)
            self.thread.start()
            self.logger.info(f"Started sensor unit {self.unit_id}")

    def stop(self):
        """Stop the sensor unit thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None

    def _process_detections(self, detections):
        """Process detection data and extract target information"""
        results = []

        for direction in [
            "north",
            "northeast",
            "east",
            "southeast",
            "south",
            "southwest",
            "west",
            "northwest",
        ]:
            if detections.HasField(direction):
                detection = getattr(detections, direction)
                detection_class = (
                    "OBSTACLE" if getattr(detection, "class") == 0 else "TARGET"
                )
                detection_distance = detection.distance
                results.append((direction, detection_class, detection_distance))

        return results

    def _command_generator(self):
        """Generate commands for the sensor unit"""
        self.logger.info(f"Initializing command generator for sensor {self.unit_id}")

        # Initial command with zero impulse
        yield simulation_pb2.UnitCommand(
            thrust=simulation_pb2.UnitCommand.ThrustCommand(
                impulse=simulation_pb2.Vector2(x=0.0, y=0.0)
            )
        )

        while self.running:
            try:
                # Get the next response
                response = self.response_queue.get()

                # Update position and navigator
                x, y = response.pos.x, response.pos.y
                self.position = (x, y)
                self.radar.draw_unit(unit_id=self.unit_id, x=x, y=y)
                # self.logger.info(f"Units coords: {x=},{y=}")
                self.navigator.update_position(self.position)

                # Process messages first to see if we need to change state
                arch_x, arch_y, timestamp = utils.get_arch_x_arch_y_from_message(
                    response
                )

                if arch_x and arch_y:
                    delta_time = time.time() - timestamp

                    if delta_time < 1.0:
                        self.state = UnitState.ATTACK
                        self.target_position = (
                            self.patrol_position[0] * 0.2 + arch_x,
                            self.patrol_position[1] * 0.2 + arch_y,
                        )
                        self.navigator.set_target(self.target_position)

                        message = f"{arch_x} {arch_y} {timestamp}"

                        # Send redundant messages t`o ensure delivery
                        self.logger.info(f"Broadcasting target at {arch_x}, {arch_y}")
                        for command in utils.send_redundant_message(
                            message, self.logger, self.unit_id
                        ):
                            yield command

                # Process detections and handle based on current state
                if response.HasField("detections"):
                    detections = self._process_detections(response.detections)

                    # Look for targets
                    for direction, detection_class, distance in detections:
                        if detection_class == "TARGET":
                            self.logger.info(
                                f"Detected TARGET in {direction} at {distance:.2f}"
                            )

                            arch_x, arch_y = utils.get_arch_centre(
                                direction, distance, x, y
                            )
                            self.radar.draw_target(arch_x, arch_y)

                            # Broadcast target info to other units
                            message = f"{arch_x} {arch_y} {time.time()}"

                            # Send redundant messages to ensure delivery
                            self.logger.info(
                                f"Broadcasting target at {arch_x}, {arch_y}"
                            )
                            for command in utils.send_redundant_message(
                                message, self.logger, self.unit_id
                            ):
                                yield command

                            # Update state to ATTACK and set target
                            self.state = UnitState.ATTACK
                            self.target_position = (arch_x, arch_y)
                            self.navigator.set_target(self.target_position)

                # Handle state-based navigation
                if self.state == UnitState.PATROL:
                    # Continue patrolling
                    navigation_impulse = self.navigator.get_navigation_impulse()
                    self.logger.debug(f"PATROL: Moving to {self.patrol_position}")

                    if self.navigator.is_at_target(arrival_threshold=2.5):
                        # Move to the next subpatrol position
                        self.subpatrol_idx = (self.subpatrol_idx + 1) % len(
                            self.subpatrol_positions
                        )
                        self.navigator.set_target(self.patrol_position)

                elif self.state == UnitState.ATTACK:
                    # We're in attack mode following the target
                    navigation_impulse = self.navigator.get_navigation_impulse()
                    self.logger.debug(
                        f"ATTACK: Following target at {self.target_position}"
                    )

                    # Return to patrol if we've followed the target for some time
                    # or if we've reached the target position
                    if self.navigator.is_at_target(arrival_threshold=10.0):
                        self.logger.info("Reached target position, returning to patrol")
                        self.state = UnitState.PATROL
                        self.navigator.set_target(self.patrol_position)
                        navigation_impulse = self.navigator.get_navigation_impulse()

                # Send movement command with redundancy
                self.logger.debug(
                    f"Using impulse: {navigation_impulse.x}, {navigation_impulse.y} for unit {self.unit_id}"
                )
                for command in utils.send_redundant_impulse(
                    navigation_impulse, self.logger, self.unit_id
                ):
                    yield command

            except Exception as e:
                self.logger.error(f"Error in command generator: {e}")

    def _control_loop(self):
        """Main control loop for the sensor unit"""
        try:
            # Create gRPC channel and stub
            channel = grpc.insecure_channel(self.server_address)
            stub = simulation_pb2_grpc.SimulationStub(channel)

            # Metadata for authentication and unit identification
            metadata = [
                ("authorization", f"bearer {self.auth_token}"),
                ("x-simulation-id", self.simulation_id),
                ("x-unit-id", self.unit_id),
            ]

            # Initialize command generator
            command_generator = self._command_generator()

            # Start bidirectional stream
            responses = stub.UnitControl(command_generator, metadata=metadata)

            # Process responses
            for response in responses:
                if not self.running:
                    break
                self.response_queue.put(response)

        except Exception as e:
            self.logger.error(f"Control loop error: {e}")
        finally:
            self.logger.info(f"Control loop for unit {self.unit_id} terminated")


class StrikeUnit:
    """A strike unit that moves to attack targets"""

    def __init__(self, unit_id, simulation_id, server_address, auth_token, radar):
        self.unit_id = unit_id
        self.simulation_id = simulation_id
        self.server_address = server_address
        self.auth_token = auth_token
        self.position = (0.0, 0.0)
        self.logger = logging.getLogger(f"strike-{unit_id}")
        self.response_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.radar = radar

        # Target tracking
        self.target_position = None

        # Navigation
        self.navigator = UnitNavigator()
        self.logger.info(f"Strike unit {unit_id} initialized and ready")

    def start(self):
        """Start the strike unit in a background thread"""
        if self.thread is None:
            self.running = True
            self.thread = threading.Thread(target=self._control_loop, daemon=True)
            self.thread.start()
            self.logger.info(f"Started strike unit {self.unit_id}")

    def stop(self):
        """Stop the strike unit thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None

    def _command_generator(self):
        """Generate commands for the strike unit"""
        self.logger.info(
            f"Initializing command generator for strike unit {self.unit_id}"
        )

        self.navigator.set_target((0, 0))
        # Initial command with zero impulse
        yield simulation_pb2.UnitCommand(
            thrust=simulation_pb2.UnitCommand.ThrustCommand(
                impulse=simulation_pb2.Vector2(x=0.0, y=0.0)
            )
        )

        while self.running:
            try:
                # Get the next response
                response = self.response_queue.get()

                # Update position and navigator
                x, y = response.pos.x, response.pos.y
                self.position = (x, y)
                self.navigator.update_position(self.position)
                self.radar.draw_unit(
                    unit_id=self.unit_id, x=x, y=y, color=(247, 5, 191)
                )

                # Process messages first to see if we need to change state
                arch_x, arch_y, timestamp = utils.get_arch_x_arch_y_from_message(
                    response
                )

                if arch_x and arch_y:
                    delta_time = time.time() - timestamp

                    if delta_time < 1.0:
                        self.target_position = (arch_x, arch_y)
                        self.navigator.set_target(self.target_position)

                        message = f"{arch_x} {arch_y} {timestamp}"

                        # Send redundant messages t`o ensure delivery
                        self.logger.info(f"Broadcasting target at {arch_x}, {arch_y}")
                        for command in utils.send_redundant_message(
                            message, self.logger, self.unit_id
                        ):
                            yield command
                elif self.navigator.is_at_target(arrival_threshold=10.0):
                    self.navigator.set_target((0, 0))

                navigation_impulse = self.navigator.get_navigation_impulse()

                # Send movement command with redundancy
                self.logger.debug(
                    f"Using impulse: {navigation_impulse.x}, {navigation_impulse.y} for unit {self.unit_id}"
                )
                for command in utils.send_redundant_impulse(
                    navigation_impulse, self.logger, self.unit_id
                ):
                    yield command

            except Exception as e:
                self.logger.error(f"Error in command generator: {e}")

    def _control_loop(self):
        """Main control loop for the strike unit"""
        try:
            # Create gRPC channel and stub
            channel = grpc.insecure_channel(self.server_address)
            stub = simulation_pb2_grpc.SimulationStub(channel)

            # Metadata for authentication and unit identification
            metadata = [
                ("authorization", f"bearer {self.auth_token}"),
                ("x-simulation-id", self.simulation_id),
                ("x-unit-id", self.unit_id),
            ]

            # Initialize command generator
            command_generator = self._command_generator()

            # Start bidirectional stream
            responses = stub.UnitControl(command_generator, metadata=metadata)

            # Process responses
            for response in responses:
                if not self.running:
                    break
                self.response_queue.put(response)

        except Exception as e:
            self.logger.error(f"Control loop error: {e}")
        finally:
            self.logger.info(f"Control loop for strike unit terminated")
