"""
Helsing Tactical Simulation Controller

This module provides a clean, object-oriented interface for controlling 
simulation units in the Helsing tactical challenge.
"""

import logging
import threading
import time
import queue
from typing import Dict, List, Tuple, Optional, Any, Generator

import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.wrappers_pb2 import StringValue
from google.protobuf import any_pb2

import simulation_pb2
import simulation_pb2_grpc
from navigation import UnitNavigator

# Configure logging
logger = logging.getLogger("simulation")


class SimulationConfig:
    """Configuration for the simulation"""
    
    def __init__(self, server_address: str, auth_token: str):
        self.server_address = server_address
        self.auth_token = auth_token
        self.metadata_base = [("authorization", f"bearer {auth_token}")]


class Detection:
    """Represents a detected object"""
    
    def __init__(self, direction: str, detection_class: str, distance: float):
        self.direction = direction
        self.detection_class = detection_class
        self.distance = distance
    
    def is_target(self) -> bool:
        return self.detection_class == "TARGET"
    
    def __repr__(self) -> str:
        return f"Detection({self.direction}, {self.detection_class}, {self.distance})"


class Message:
    """Represents a message between units"""
    
    def __init__(self, source_id: str, content: Any):
        self.source_id = source_id
        self.content = content
    
    def __repr__(self) -> str:
        return f"Message(from={self.source_id}, content={self.content})"


class BaseUnit:
    """Base class for all units in the simulation"""
    
    def __init__(self, unit_id: str, simulation_id: str, config: SimulationConfig):
        self.unit_id = unit_id
        self.simulation_id = simulation_id
        self.config = config
        self.position = (0.0, 0.0)
        self.response_queue = queue.Queue()
        self.logger = logging.getLogger(f"{self.__class__.__name__}-{unit_id}")
        self.channel = None
        self.stub = None
        self.running = False
        self.thread = None
    
    def initialize_grpc(self) -> None:
        """Initialize gRPC channel and stub"""
        self.channel = grpc.insecure_channel(self.config.server_address)
        self.stub = simulation_pb2_grpc.SimulationStub(self.channel)
    
    def get_metadata(self) -> List[Tuple[str, str]]:
        """Get metadata for gRPC calls"""
        return self.config.metadata_base + [
            ("x-simulation-id", self.simulation_id),
            ("x-unit-id", self.unit_id),
        ]
    
    def update_position(self, pos_x: float, pos_y: float) -> None:
        """Update the unit's position"""
        self.position = (pos_x, pos_y)
    
    def process_response(self, response) -> None:
        """Process a response from the server"""
        if hasattr(response, "pos"):
            self.update_position(response.pos.x, response.pos.y)
        self.response_queue.put(response)
    
    def start(self) -> None:
        """Start the unit control thread"""
        if not self.thread:
            self.running = True
            self.initialize_grpc()
            self.thread = threading.Thread(target=self._control_loop, daemon=True)
            self.thread.start()
            self.logger.info(f"Started unit {self.unit_id}")
    
    def stop(self) -> None:
        """Stop the unit control thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
    
    def _control_loop(self) -> None:
        """Main control loop to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _control_loop")
    
    def _command_generator(self) -> Generator:
        """Generate commands to be sent to the server"""
        raise NotImplementedError("Subclasses must implement _command_generator")


class SensorUnit(BaseUnit):
    """A sensor unit that can detect objects and communicate with other units"""
    
    def __init__(self, unit_id: str, simulation_id: str, config: SimulationConfig, 
                 start_position: Optional[Tuple[float, float]] = None):
        super().__init__(unit_id, simulation_id, config)
        self.detections = []
        self.messages = []
        self.navigator = UnitNavigator()
        
        # Predefined patrol points for sensors to move between
        patrol_positions = [(50, 50), (-50, 50), (-50, -50), (50, -50)]
        idx = (int(unit_id) - 1) % len(patrol_positions)
        self.patrol_position = patrol_positions[idx]
        
        if start_position:
            self.position = start_position
    
    def parse_detections(self, detection_obj) -> List[Detection]:
        """Parse detection objects from the response"""
        results = []
        for direction in ["north", "northeast", "east", "southeast", 
                        "south", "southwest", "west", "northwest"]:
            if detection_obj.HasField(direction):
                detection = getattr(detection_obj, direction)
                detection_class = "OBSTACLE" if getattr(detection, "class") == 0 else "TARGET"
                detection_distance = detection.distance
                results.append(Detection(direction, detection_class, detection_distance))
        return results
    
    def _command_generator(self) -> Generator:
        """Generate commands for the sensor unit"""
        # Initial command to start things off
        self.logger.info(f"Initializing command generator for sensor {self.unit_id}")
        
        # Set initial patrol position
        self.navigator.set_target(self.patrol_position)
        
        # Send initial command
        yield simulation_pb2.UnitCommand(
            thrust=simulation_pb2.UnitCommand.ThrustCommand(
                impulse=simulation_pb2.Vector2(x=0.0, y=0.0)
            )
        )
        
        while self.running:
            try:
                # Get the next response
                response = self.response_queue.get(timeout=1.0)
                
                # Update navigator with current position
                current_pos = (response.pos.x, response.pos.y)
                self.navigator.update_position(current_pos)
                
                # Check for detections
                if response.HasField("detections"):
                    self.detections = self.parse_detections(response.detections)
                    
                    # Log any target detections
                    targets = [d for d in self.detections if d.is_target()]
                    if targets:
                        for target in targets:
                            self.logger.info(f"Detected TARGET in {target.direction} at {target.distance:.2f}")
                            
                            # Broadcast target info to other units
                            message = f"TARGET_DETECTED|{target.direction}|{target.distance:.2f}"
                            string_value = StringValue(value=message)
                            
                            any_message = any_pb2.Any()
                            any_message.Pack(string_value)
                            
                            yield simulation_pb2.UnitCommand(
                                msg=simulation_pb2.UnitCommand.MsgCommand(msg=any_message)
                            )
                            # Skip movement command this cycle if we sent a message
                            continue
                
                # Get navigation impulse
                navigation_impulse = self.navigator.get_navigation_impulse()
                
                # Send movement command
                yield simulation_pb2.UnitCommand(
                    thrust=simulation_pb2.UnitCommand.ThrustCommand(
                        impulse=navigation_impulse
                    )
                )
                
                # Switch patrol position if we've reached the current target
                if self.navigator.is_at_target():
                    # Simple rotation of patrol positions
                    patrol_positions = [(50, 50), (-50, 50), (-50, -50), (50, -50)]
                    current_idx = patrol_positions.index(self.patrol_position)
                    next_idx = (current_idx + 1) % len(patrol_positions)
                    self.patrol_position = patrol_positions[next_idx]
                    self.navigator.set_target(self.patrol_position)
                    self.logger.info(f"Reached patrol point, moving to next: {self.patrol_position}")
                
            except queue.Empty:
                # If no response received, just continue
                pass
            except Exception as e:
                self.logger.error(f"Error in command generator: {e}")
    
    def _control_loop(self) -> None:
        """Main control loop for the sensor unit"""
        try:
            # Initialize command generator
            command_generator = self._command_generator()
            
            # Start bidirectional stream
            metadata = self.get_metadata()
            responses = self.stub.UnitControl(command_generator, metadata=metadata)
            
            # Process responses
            for response in responses:
                if not self.running:
                    break
                self.process_response(response)
                
        except Exception as e:
            self.logger.error(f"Control loop error: {e}")
        finally:
            self.logger.info(f"Control loop for unit {self.unit_id} terminated")


class StrikeUnit(BaseUnit):
    """A strike unit that can move to attack targets"""
    
    def __init__(self, unit_id: str, simulation_id: str, config: SimulationConfig):
        super().__init__(unit_id, simulation_id, config)
        self.has_target_info = False
        self.target_direction = None
        self.target_distance = None
        self.target_position = None
        self.counter = 0
        self.navigator = UnitNavigator()
        self.search_pattern_idx = 0
        self.search_patterns = [(20.0, 20.0), (-20.0, 20.0), (-20.0, -20.0), (20.0, -20.0)]
    
    def _command_generator(self) -> Generator:
        """Generate commands for the strike unit"""
        self.logger.info("Initializing command generator for strike unit")
        
        # Initial command
        yield simulation_pb2.UnitCommand()
        
        while self.running:
            try:
                # Get the next response
                response = self.response_queue.get(timeout=1.0)
                
                # Update navigator with current position
                current_pos = (response.pos.x, response.pos.y)
                self.navigator.update_position(current_pos)
                
                # Process messages to look for target information
                self._process_messages(response)
                
                # Increment counter for search patterns
                self.counter += 1
                
                # Create movement command based on current state
                if self.has_target_info:
                    # If we have a target position, use the navigator to get there
                    if self.target_position:
                        # Already have calculated position, navigate to it
                        self.navigator.set_target(self.target_position)
                        nav_impulse = self.navigator.get_navigation_impulse()
                        self.logger.info(f"Moving toward target at {self.target_position}, impulse={nav_impulse.x},{nav_impulse.y}")
                        
                        yield simulation_pb2.UnitCommand(
                            thrust=simulation_pb2.UnitCommand.ThrustCommand(impulse=nav_impulse)
                        )
                    else:
                        # Convert direction+distance to estimated position
                        self._update_target_position_from_direction()
                        
                        # First time we need to set the target
                        self.navigator.set_target(self.target_position)
                        nav_impulse = self.navigator.get_navigation_impulse()
                        self.logger.info(f"Initial move toward target at {self.target_position}, impulse={nav_impulse.x},{nav_impulse.y}")
                        
                        yield simulation_pb2.UnitCommand(
                            thrust=simulation_pb2.UnitCommand.ThrustCommand(impulse=nav_impulse)
                        )
                else:
                    # No target info - navigate to next search pattern position
                    current_search_pos = self.search_patterns[self.search_pattern_idx]
                    
                    # Check if we've reached the current search position
                    if self.navigator.target_pos == current_search_pos and self.navigator.is_at_target():
                        # Move to next search position
                        self.search_pattern_idx = (self.search_pattern_idx + 1) % len(self.search_patterns)
                        current_search_pos = self.search_patterns[self.search_pattern_idx]
                        self.logger.info(f"Reached search point, moving to next: {current_search_pos}")
                    
                    # Set target for navigation
                    self.navigator.set_target(current_search_pos)
                    nav_impulse = self.navigator.get_navigation_impulse()
                    
                    self.logger.info(f"Searching: pattern={self.search_pattern_idx}, target={current_search_pos}, impulse={nav_impulse.x},{nav_impulse.y}")
                    
                    yield simulation_pb2.UnitCommand(
                        thrust=simulation_pb2.UnitCommand.ThrustCommand(impulse=nav_impulse)
                    )
                
            except queue.Empty:
                # If no response received, just continue
                pass
            except Exception as e:
                self.logger.error(f"Error in command generator: {e}")
    
    def _process_messages(self, response) -> None:
        """Process messages to extract target information"""
        if response.messages:
            for message in response.messages:
                msg_str = str(message.value)
                if "TARGET_DETECTED" in msg_str:
                    parts = msg_str.split('|')
                    if len(parts) >= 3:
                        self.has_target_info = True
                        self.target_direction = parts[1]
                        try:
                            self.target_distance = float(parts[2])
                            # Reset target position to recalculate
                            self.target_position = None
                            self.logger.info(f"Received target info: direction={parts[1]}, distance={self.target_distance}")
                        except (ValueError, IndexError):
                            self.logger.error(f"Invalid distance format in message: {msg_str}")
    
    def _update_target_position_from_direction(self) -> None:
        """Convert direction and distance to an estimated target position"""
        if not self.has_target_info or not self.target_direction or not self.target_distance:
            return
        
        # Get current position
        x, y = self.position
        
        # Direction vectors (normalized)
        direction_vectors = {
            "north": (0.0, 1.0),
            "northeast": (0.7071, 0.7071),
            "east": (1.0, 0.0),
            "southeast": (0.7071, -0.7071),
            "south": (0.0, -1.0),
            "southwest": (-0.7071, -0.7071),
            "west": (-1.0, 0.0),
            "northwest": (-0.7071, 0.7071)
        }
        
        # Get direction vector
        dx, dy = direction_vectors.get(self.target_direction, (0.0, 0.0))
        
        # Calculate target position
        target_x = x + dx * self.target_distance
        target_y = y + dy * self.target_distance
        
        self.target_position = (target_x, target_y)
        self.logger.info(f"Calculated target position: {self.target_position}")
        
    def _direction_to_vector(self, direction: str) -> simulation_pb2.Vector2:
        """Convert a cardinal direction to a Vector2"""
        direction_map = {
            "north": (0.0, 5.0),
            "northeast": (3.5, 3.5),
            "east": (5.0, 0.0),
            "southeast": (3.5, -3.5),
            "south": (0.0, -5.0),
            "southwest": (-3.5, -3.5),
            "west": (-5.0, 0.0),
            "northwest": (-3.5, 3.5)
        }
        
        x, y = direction_map.get(direction, (0.0, 0.0))
        return simulation_pb2.Vector2(x=x, y=y)
    
    def _control_loop(self) -> None:
        """Main control loop for the strike unit"""
        try:
            # Initialize command generator
            command_generator = self._command_generator()
            
            # Start bidirectional stream
            metadata = self.get_metadata()
            responses = self.stub.UnitControl(command_generator, metadata=metadata)
            
            # Process responses
            for response in responses:
                if not self.running:
                    break
                self.process_response(response)
                
        except Exception as e:
            self.logger.error(f"Control loop error: {e}")
        finally:
            self.logger.info(f"Control loop for strike unit terminated")


class SimulationController:
    """Main controller for the simulation"""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.simulation_id = None
        self.base_position = None
        self.sensor_units = {}
        self.strike_unit = None
        self.logger = logging.getLogger("simulation")
    
    def start_simulation(self) -> bool:
        """Start a new simulation"""
        try:
            self.logger.info("Starting new simulation")
            
            # Create gRPC channel and stub
            with grpc.insecure_channel(self.config.server_address) as channel:
                stub = simulation_pb2_grpc.SimulationStub(channel)
                
                # Start simulation
                response = stub.Start(Empty(), metadata=self.config.metadata_base)
                
                # Store simulation parameters
                self.simulation_id = response.id
                self.base_position = (response.base_pos.x, response.base_pos.y)
                
                # Log simulation parameters
                self.logger.info(f"Simulation started with ID: {self.simulation_id}")
                self.logger.info(f"Base position: ({self.base_position[0]}, {self.base_position[1]})")
                self.logger.info(f"Sensor units: {len(response.sensor_units)}")
                
                # Create sensor units
                for unit_id, pos in response.sensor_units.items():
                    start_pos = (pos.x, pos.y)
                    self.logger.info(f"  Unit {unit_id}: ({start_pos[0]}, {start_pos[1]})")
                    self.sensor_units[unit_id] = SensorUnit(
                        unit_id=unit_id,
                        simulation_id=self.simulation_id,
                        config=self.config,
                        start_position=start_pos
                    )
                
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to start simulation: {e}")
            return False
    
    def launch_strike_unit(self) -> bool:
        """Launch the strike unit"""
        if not self.simulation_id:
            self.logger.error("Cannot launch strike unit: no active simulation")
            return False
        
        try:
            self.logger.info(f"Launching strike unit for simulation {self.simulation_id}")
            
            # Create gRPC channel and stub
            with grpc.insecure_channel(self.config.server_address) as channel:
                stub = simulation_pb2_grpc.SimulationStub(channel)
                
                # Launch strike unit
                request = StringValue(value=self.simulation_id)
                response = stub.LaunchStrikeUnit(
                    request, 
                    metadata=self.config.metadata_base
                )
                
                # Calculate distance from base
                dx = response.pos.x - self.base_position[0]
                dy = response.pos.y - self.base_position[1]
                distance = (dx**2 + dy**2)**0.5
                
                # Log strike unit details
                unit_id = response.id
                self.logger.info(f"Strike unit {unit_id} launched at position ({response.pos.x}, {response.pos.y})")
                self.logger.info(f"Distance from base: {distance:.2f} units, Offset: ({dx:.2f}, {dy:.2f})")
                
                # Create strike unit
                self.strike_unit = StrikeUnit(
                    unit_id=unit_id,
                    simulation_id=self.simulation_id,
                    config=self.config
                )
                
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to launch strike unit: {e}")
            return False
    
    def get_simulation_status(self) -> Optional[int]:
        """Get the current status of the simulation"""
        if not self.simulation_id:
            self.logger.error("Cannot get status: no active simulation")
            return None
        
        try:
            # Create gRPC channel and stub
            with grpc.insecure_channel(self.config.server_address) as channel:
                stub = simulation_pb2_grpc.SimulationStub(channel)
                
                # Get simulation status
                request = StringValue(value=self.simulation_id)
                response = stub.GetSimulationStatus(
                    request, 
                    metadata=self.config.metadata_base
                )
                
                # Log simulation status
                if hasattr(response, "status"):
                    status_map = {0: "RUNNING", 1: "SUCCESS", 2: "TIMED_OUT", 3: "CANCELED"}
                    status_str = status_map.get(response.status, str(response.status))
                    self.logger.info(f"Simulation status: {status_str}")
                    return response.status
                
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get simulation status: {e}")
            return None
    
    def run(self, launch_strike_delay: float = 5.0) -> None:
        """Run the simulation from start to finish"""
        # Start a new simulation
        if not self.start_simulation():
            return
        
        # Start all sensor units
        for sensor_unit in self.sensor_units.values():
            sensor_unit.start()
        
        # Wait before launching strike unit
        if launch_strike_delay > 0:
            self.logger.info(f"Sensors activated. Waiting {launch_strike_delay} seconds before launching strike unit...")
            time.sleep(launch_strike_delay)
            
            # Launch and start strike unit
            if self.launch_strike_unit():
                self.strike_unit.start()
        
        # Monitor simulation status
        try:
            self.logger.info("Simulation running, press Ctrl+C to exit...")
            while True:
                time.sleep(5)
                status = self.get_simulation_status()
                
                if status is not None and status != 0:  # Not RUNNING
                    status_map = {1: "SUCCESS", 2: "TIMED_OUT", 3: "CANCELED"}
                    status_str = status_map.get(status, str(status))
                    self.logger.info(f"Simulation ended with status: {status_str}")
                    break
                    
        except KeyboardInterrupt:
            self.logger.info("Simulation interrupted by user")
        finally:
            # Stop all units
            for sensor_unit in self.sensor_units.values():
                sensor_unit.stop()
            
            if self.strike_unit:
                self.strike_unit.stop() 