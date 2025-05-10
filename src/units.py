"""
Units for Helsing tactical simulation

Contains the SensorUnit and StrikeUnit implementations.
"""

import logging
import threading
import queue
import grpc
from google.protobuf.wrappers_pb2 import StringValue
from google.protobuf import any_pb2

import simulation_pb2
import simulation_pb2_grpc
from navigation import UnitNavigator

# Configure module logger
logger = logging.getLogger("units")


class SensorUnit:
    """A sensor unit that detects targets and broadcasts information"""
    
    def __init__(self, unit_id, simulation_id, server_address, auth_token, start_position=None):
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
        
        # Set patrol position based on unit ID
        patrol_positions = [(50, 50), (-50, 50), (50, -50), (-50, -50)]
        idx = int(unit_id) - 1
        self.patrol_position = patrol_positions[idx]
        self.navigator.set_target(self.patrol_position)
    
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
        
        for direction in ["north", "northeast", "east", "southeast", 
                          "south", "southwest", "west", "northwest"]:
            if detections.HasField(direction):
                detection = getattr(detections, direction)
                detection_class = "OBSTACLE" if getattr(detection, "class") == 0 else "TARGET"
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
                self.navigator.update_position(self.position)
                
                # Check for detections
                if response.HasField("detections"):
                    detections = self._process_detections(response.detections)
                    
                    # Look for targets
                    for direction, detection_class, distance in detections:
                        if detection_class == "TARGET":
                            self.logger.info(f"Detected TARGET in {direction} at {distance:.2f}")
                            
                            # Broadcast target info to other units
                            message = f"TARGET_DETECTED|{direction}|{distance:.2f}"
                            string_value = StringValue(value=message)
                            
                            #TODO: send right info
                            
                            any_message = any_pb2.Any()
                            any_message.Pack(string_value)
                            
                            yield simulation_pb2.UnitCommand(
                                msg=simulation_pb2.UnitCommand.MsgCommand(msg=any_message)
                            )
                            
                
                # Get navigation impulse
                navigation_impulse = self.navigator.get_navigation_impulse()
                
                # Send movement command
                yield simulation_pb2.UnitCommand(
                    thrust=simulation_pb2.UnitCommand.ThrustCommand(
                        impulse=navigation_impulse
                    )
                )
                
                # # Switch patrol position if we've reached the current target
                # if self.navigator.is_at_target():
                #     # Simple rotation of patrol positions
                #     patrol_positions = [(50, 50), (-50, 50), (-50, -50), (50, -50)]
                #     current_idx = patrol_positions.index(self.patrol_position)
                #     next_idx = (current_idx + 1) % len(patrol_positions)
                #     self.patrol_position = patrol_positions[next_idx]
                #     self.navigator.set_target(self.patrol_position)
                #     self.logger.info(f"Reached patrol point, moving to next: {self.patrol_position}")

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
    
    def __init__(self, unit_id, simulation_id, server_address, auth_token):
        self.unit_id = unit_id
        self.simulation_id = simulation_id
        self.server_address = server_address
        self.auth_token = auth_token
        self.position = (0.0, 0.0)
        self.logger = logging.getLogger(f"strike-{unit_id}")
        self.response_queue = queue.Queue()
        self.running = False
        self.thread = None
        
        # Target tracking
        self.target_position = None
        
        # Navigation
        self.navigator = UnitNavigator()
    
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
    
    def _update_target_position(self):
        """Calculate target position from direction and distance"""
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
    
    def _command_generator(self):
        """Generate commands for the strike unit"""
        self.logger.info(f"Initializing command generator for strike unit {self.unit_id}")
        
        # Initial command with zero impulse
        yield simulation_pb2.UnitCommand()
        
        while self.running:
            try:
                # Get the next response
                response = self.response_queue.get()
                
                # Update position and navigator
                x, y = response.pos.x, response.pos.y
                self.position = (x, y)
                self.navigator.update_position(self.position)
                
                # Process messages to look for target information
                
                #TODO: process response message and send right message
                
                yield simulation_pb2.UnitCommand(
                    thrust=simulation_pb2.UnitCommand.ThrustCommand(
                        impulse=None
                    )
                )
                
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