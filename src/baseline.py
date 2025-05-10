import os
import random
from dotenv import load_dotenv
import grpc
import time
import simulation_pb2
import simulation_pb2_grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.wrappers_pb2 import StringValue
import threading
from queue import Queue
import queue
from google.protobuf import any_pb2
import logging
import sys
from navigation import UnitNavigator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Create named loggers
logger = logging.getLogger("simulation")
sensor_logger = logging.getLogger("sensor")
strike_logger = logging.getLogger("strike")

load_dotenv()

# Server address and port
SERVER_ADDRESS = "172.237.124.96:21234"
TOKEN = ''.join(os.urandom(40).hex())  # Generate 40 random bytes and convert to hex string

# Create thread-safe queues
response_queue = Queue()

def start_simulation():
    """Start a new simulation and return the simulation parameters"""
    logger.info("Starting new simulation")
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)
        
        response = stub.Start(Empty(), metadata=[("authorization", f"bearer {TOKEN}")])
        logger.info(f"Simulation started with ID: {response.id}")
        return response

def check_detection(detections):
    result = []
    for direction in ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]:
        if detections.HasField(direction):
            detection: simulation_pb2.Detection = getattr(detections, direction)
            detection_class = "OBSTACLE" if getattr(detection, "class") == 0 else "TARGET"
            detection_distance = detection.distance
            result.append((direction, detection_class, detection_distance))
    return result

def control_sensor_unit(simulation_id, unit_id):
    """Control a specific sensor unit"""
    unit_logger = logging.getLogger(f"sensor-{unit_id}")
    unit_logger.info(f"Initializing sensor unit {unit_id} for simulation {simulation_id}")
    
    channel = grpc.insecure_channel(SERVER_ADDRESS)
    stub = simulation_pb2_grpc.SimulationStub(channel)
    
    start_positions = [(50, 50), (-50, 50), (-50, -50), (50, -50)] 
    
    # Metadata for this unit
    metadata = [
        ("authorization", f"bearer {TOKEN}"),
        ("x-simulation-id", simulation_id),
        ("x-unit-id", unit_id),
    ]
    
    # Shared state between response handler and command generator
    response_queue = Queue()
    
    unit_navigator = UnitNavigator()
    unit_navigator.set_target(start_positions[int(unit_id) - 1])
    
    # Create a generator for sending commands
    def generate_commands():
        unit_logger.info(f"Sending initial command for unit {unit_id}")
        yield simulation_pb2.UnitCommand(
            thrust=simulation_pb2.UnitCommand.ThrustCommand(
                impulse=simulation_pb2.Vector2(x=0.0, y=0.0)
            )
        )
        
        while True:
            response = response_queue.get()
            
            x = response.pos.x
            y = response.pos.y
            unit_navigator.update_position((x, y))
            
            # unit_logger.info(f"Current position: ({x}, {y})")
            
            navigation_impulse = unit_navigator.get_navigation_impulse()
            
            # Log navigation details
            # # unit_logger.info(f"  Current velocity: {unit_navigator.estimated_velocity}")
            # # unit_logger.info(f"  Distance to target: {((x**2 + y**2)**0.5):.2f}")
            # # unit_logger.info(f"  At target: {unit_navigator.is_at_target()}")
            # unit_logger.info(f"  Nav impulse: {navigation_impulse}")
            detections = check_detection(response.detections)
            has_target = any("TARGET" == detection[1] for detection in detections)
             
            if has_target:
                unit_logger.info(f"{x=} {y=}: {check_detection(response.detections)}")
            
            yield simulation_pb2.UnitCommand(
                    thrust=simulation_pb2.UnitCommand.ThrustCommand(
                        impulse=navigation_impulse 
                    )
                )        
    
    # Start the bidirectional streaming
    unit_logger.info(f"Starting bidirectional stream for unit {unit_id}")
    responses = stub.UnitControl(generate_commands(), metadata=metadata)
    
    # Process the responses
    for response in responses:
        unit_logger.debug(f"Unit {unit_id} position: ({response.pos.x}, {response.pos.y})")
        
        if response.HasField("detections"):
            detections = response.detections
            
            for direction in ["north", "northeast", "east", "southeast", 
                             "south", "southwest", "west", "northwest"]:
                if detections.HasField(direction):
                    detection = getattr(detections, direction)
                    cls_value = getattr(detection, "class")
                    cls_name = "OBSTACLE" if cls_value == 0 else "TARGET"
                    unit_logger.debug(f"Unit {unit_id} detected {cls_name} {direction.upper()} at {detection.distance}")
                
        if response.messages:
            for message in response.messages:
                unit_logger.debug(f"Unit {unit_id} received message from {message.src}")
        
        # Add response to the queue for the generator to process
        response_queue.put(response)

def launch_strike_unit(simulation_id, base_pos):
    """Launch the strike unit"""
    logger.info(f"Launching strike unit for simulation {simulation_id}")
    
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)
        
        request = StringValue(value=simulation_id)
        response = stub.LaunchStrikeUnit(request, metadata=[("authorization", f"bearer {TOKEN}")])
        
        # Calculate distance from base
        dx = response.pos.x - base_pos.x
        dy = response.pos.y - base_pos.y
        distance_from_base = (dx**2 + dy**2)**0.5
        
        logger.info(f"Strike unit {response.id} launched at position ({response.pos.x}, {response.pos.y})")
        logger.info(f"Distance from base: {distance_from_base:.2f} units, Offset: ({dx:.2f}, {dy:.2f})")
        
        return response

def control_strike_unit(simulation_id, unit_id):
    """Control the strike unit"""
    unit_logger = logging.getLogger(f"strike-{unit_id}")
    unit_logger.info(f"Initializing strike unit {unit_id} for simulation {simulation_id}")
    
    channel = grpc.insecure_channel(SERVER_ADDRESS)
    stub = simulation_pb2_grpc.SimulationStub(channel)
    
    # Metadata for this unit
    metadata = [
        ("authorization", f"bearer {TOKEN}"),
        ("x-simulation-id", simulation_id),
        ("x-unit-id", unit_id),
    ]
    
    # Shared state between response handler and command generator
    response_queue = Queue()
    strike_state = {
        "has_target_info": False,
        "target_direction": None,
        "counter": 0
    }
    
    # Create a generator for sending commands
    def generate_commands():
        # Initial command
        unit_logger.info("Sending initial strike unit command")
        yield simulation_pb2.UnitCommand()
        
        while True:
            # Wait for response (blocking)
            try:
                unit_logger.debug("Strike unit waiting for response")
                response = response_queue.get()
                unit_logger.debug("Strike unit received response")
                
                # Process messages
                for message in response.messages:
                    msg_str = str(message.value)
                    if "TARGET_DETECTED" in msg_str:
                        parts = msg_str.split('|')
                        if len(parts) >= 2:
                            strike_state["has_target_info"] = True
                            strike_state["target_direction"] = parts[1]
                            unit_logger.info(f"Strike unit received target info: direction={parts[1]}")
                
                # Increment counter
                strike_state["counter"] += 1
                
                # Simple condition: If we have target info, move toward it
                if strike_state["has_target_info"]:
                    # Similar direction mapping as above
                    if strike_state["target_direction"] == "north":
                        vector = simulation_pb2.Vector2(x=0.0, y=1.0)
                    elif strike_state["target_direction"] == "northeast":
                        vector = simulation_pb2.Vector2(x=0.7, y=0.7)
                    elif strike_state["target_direction"] == "east":
                        vector = simulation_pb2.Vector2(x=1.0, y=0.0)
                    elif strike_state["target_direction"] == "southeast":
                        vector = simulation_pb2.Vector2(x=0.7, y=-0.7)
                    elif strike_state["target_direction"] == "south":
                        vector = simulation_pb2.Vector2(x=0.0, y=-1.0)
                    elif strike_state["target_direction"] == "southwest":
                        vector = simulation_pb2.Vector2(x=-0.7, y=-0.7)
                    elif strike_state["target_direction"] == "west":
                        vector = simulation_pb2.Vector2(x=-1.0, y=0.0)
                    elif strike_state["target_direction"] == "northwest":
                        vector = simulation_pb2.Vector2(x=-0.7, y=0.7)
                    else:
                        vector = simulation_pb2.Vector2(x=0.0, y=0.0)
                    
                    unit_logger.info(f"Strike unit moving toward target in {strike_state['target_direction']}")
                else:
                    # No target info - just make a simple circular motion
                    directions = [(0.5, 0.5), (-0.5, 0.5), (-0.5, -0.5), (0.5, -0.5)]
                    idx = (strike_state["counter"] % 4)
                    vector = simulation_pb2.Vector2(x=directions[idx][0], y=directions[idx][1])
                    unit_logger.info(f"Strike unit searching: direction={idx}, vector=({directions[idx][0]}, {directions[idx][1]})")
                
                yield simulation_pb2.UnitCommand(
                    thrust=simulation_pb2.UnitCommand.ThrustCommand(impulse=vector)
                )
                
            except queue.Empty:
                # This should never happen with blocking get()
                unit_logger.error("Strike unit queue.Empty exception - should not happen with blocking get()")
                pass
    
    # Start the bidirectional streaming
    unit_logger.info("Starting bidirectional stream for strike unit")
    responses = stub.UnitControl(generate_commands(), metadata=metadata)
    
    # Process the responses
    for response in responses:
        unit_logger.debug(f"Strike unit position: ({response.pos.x}, {response.pos.y})")
        
        if response.messages:
            for message in response.messages:
                unit_logger.debug(f"Strike unit received message from {message.src}")
        
        # Add response to the queue for the generator to process
        response_queue.put(response)

def get_simulation_status(simulation_id):
    """Get the status of a simulation"""
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)
        
        request = StringValue(value=simulation_id)
        response = stub.GetSimulationStatus(request, metadata=[("authorization", f"bearer {TOKEN}")])
        
        if hasattr(response, "status"):
            status_map = {0: "RUNNING", 1: "SUCCESS", 2: "TIMED_OUT", 3: "CANCELED"}
            status_str = status_map.get(response.status, str(response.status))
            logger.info(f"Simulation status: {status_str}")
        
        return response

if __name__ == "__main__":
    # Start a new simulation
    sim_response = start_simulation()
    simulation_id = sim_response.id
    
    logger.info(f"Base position: ({sim_response.base_pos.x}, {sim_response.base_pos.y})")
    logger.info(f"Sensor units: {len(sim_response.sensor_units)}")
    for unit_id, pos in sim_response.sensor_units.items():
        logger.info(f"  Unit {unit_id}: ({pos.x}, {pos.y})")
    
    # Single unit version 
    # control_sensor_unit(simulation_id=simulation_id, unit_id="1", initial_pos=(sim_response.sensor_units["1"].x, sim_response.sensor_units["1"].y))
    
    # Start all sensor units in separate threads
    sensor_threads = []
    for sensor_id in sim_response.sensor_units.keys():
        sensor_thread = threading.Thread(
            target=control_sensor_unit,
            args=(simulation_id, sensor_id),
            daemon=True
        )
        sensor_threads.append(sensor_thread)
        sensor_thread.start()
        logger.info(f"Started sensor unit {sensor_id}")
    
    # Wait for some time to let the sensors start moving and detecting
    # logger.info("Sensors activated. Waiting 5 seconds before launching strike unit...")
    # time.sleep(5)
    
    # # Launch the strike unit
    # logger.info("Launching strike unit...")
    # strike_response = launch_strike_unit(simulation_id, sim_response.base_pos)
    # strike_unit_id = strike_response.id
    
    # # Start controlling the strike unit in a separate thread
    # strike_thread = threading.Thread(
    #     target=control_strike_unit,
    #     args=(simulation_id, strike_unit_id),
    #     daemon=True
    # )
    # strike_thread.start()
    # logger.info(f"Strike unit {strike_unit_id} activated")
    
    # Wait for the simulation to end
    logger.info("Simulation running, press Ctrl+C to exit...")
    try:
        while True:
            time.sleep(5)
            status = get_simulation_status(simulation_id)
            if hasattr(status, "status") and status.status != 0:  # Not RUNNING
                status_map = {1: "SUCCESS", 2: "TIMED_OUT", 3: "CANCELED"}
                status_str = status_map.get(status.status, str(status.status))
                logger.info(f"Simulation ended with status: {status_str}")
                break
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user") 