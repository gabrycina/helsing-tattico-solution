import os
from dotenv import load_dotenv
import grpc
import time
import simulation_pb2
import simulation_pb2_grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.wrappers_pb2 import StringValue
import threading

load_dotenv()

# Server address and port
SERVER_ADDRESS = "172.237.124.96:21234"
TOKEN = ''.join(os.urandom(40).hex())  # Generate 40 random bytes and convert to hex string

def start_simulation():
    """Start a new simulation and return the simulation parameters"""
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)
        
        response = stub.Start(Empty(), metadata=[("authorization", f"bearer {TOKEN}")])
        print("Simulation started with parameters:")
        return response

def control_sensor_unit(simulation_id, unit_id):
    """Control a specific sensor unit"""
    channel = grpc.insecure_channel(SERVER_ADDRESS)
    stub = simulation_pb2_grpc.SimulationStub(channel)
    
    # Metadata for this unit
    metadata = [
        ("authorization", f"bearer {TOKEN}"),
        ("x-simulation-id", simulation_id),
        ("x-unit-id", unit_id),
    ]
    
    # Create a generator for sending commands
    def generate_commands():
        # Wait for a moment to connect
        time.sleep(1)
        
        # Send movement command - move in positive X direction
        thrust_command = simulation_pb2.UnitCommand.ThrustCommand(
            impulse=simulation_pb2.Vector2(x=1.0, y=0.0)
        )
        command = simulation_pb2.UnitCommand(thrust=thrust_command)
        print(f"Sending movement command to unit {unit_id}: {command}")
        yield command
        
        # Keep the stream open
        while True:
            time.sleep(5)
            # Send null command to keep connection alive
            command = simulation_pb2.UnitCommand()
            yield command
    
    # Start the bidirectional streaming
    responses = stub.UnitControl(generate_commands(), metadata=metadata)
    
    # Process the responses
    for response in responses:
        print(f"\nReceived update from unit {unit_id}:")
        print(f"  Position: X={response.pos.x}, Y={response.pos.y}")
        
        if response.HasField("detections"):
            print("  Detections:")
            detections = response.detections
            
            for direction in ["north", "northeast", "east", "southeast", 
                             "south", "southwest", "west", "northwest"]:
                if detections.HasField(direction):
                    detection: simulation_pb2.Detection = getattr(detections, direction)
                    detection_class = "OBSTACLE" if getattr(detection, "class") == 0 else "TARGET"
                    print(f"    {direction.upper()}: {detection_class} at distance {detection.distance}")
                
        if response.messages:
            print("  Messages:")
            for message in response.messages:
                print(f"    From {message.src}: {message.value}")

def launch_strike_unit(simulation_id, base_pos):
    """Launch the strike unit"""
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)
        
        request = StringValue(value=simulation_id)
        response = stub.LaunchStrikeUnit(request, metadata=[("authorization", f"bearer {TOKEN}")])
        print("\nStrike unit launched:")
        print(f"  Unit ID: {response.id}")
        print(f"  Position: X={response.pos.x}, Y={response.pos.y}")
        
        # Calculate distance from base
        dx = response.pos.x - base_pos.x
        dy = response.pos.y - base_pos.y
        distance_from_base = (dx**2 + dy**2)**0.5
        
        print(f"  Distance from base: {distance_from_base:.2f} units")
        print(f"  Offset from base: X={dx:.2f}, Y={dy:.2f}")
        
        return response

def control_strike_unit(simulation_id, unit_id):
    """Control the strike unit"""
    channel = grpc.insecure_channel(SERVER_ADDRESS)
    stub = simulation_pb2_grpc.SimulationStub(channel)
    
    # Metadata for this unit
    metadata = [
        ("authorization", f"bearer {TOKEN}"),
        ("x-simulation-id", simulation_id),
        ("x-unit-id", unit_id),
    ]
    
    # Create a generator for sending commands
    def generate_commands():
        # Wait for a moment to connect
        time.sleep(1)
        
        # Send movement command - move in positive X direction
        thrust_command = simulation_pb2.UnitCommand.ThrustCommand(
            impulse=simulation_pb2.Vector2(x=1.0, y=1.0)
        )
        command = simulation_pb2.UnitCommand(thrust=thrust_command)
        print(f"Sending movement command to strike unit: {command}")
        yield command
        
        # Keep the stream open
        while True:
            time.sleep(5)
            # Send null command to keep connection alive
            command = simulation_pb2.UnitCommand()
            yield command
    
    # Start the bidirectional streaming
    responses = stub.UnitControl(generate_commands(), metadata=metadata)
    
    # Process the responses
    for response in responses:
        print(f"\nReceived update from strike unit:")
        print(f"  Position: X={response.pos.x}, Y={response.pos.y}")
        
        if response.messages:
            print("  Messages:")
            for message in response.messages:
                print(f"    From {message.src}: {message.value}")

def get_simulation_status(simulation_id):
    """Get the status of a simulation"""
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)
        
        request = StringValue(value=simulation_id)
        response = stub.GetSimulationStatus(request, metadata=[("authorization", f"bearer {TOKEN}")])
        print("\nSimulation status:")
        print(response)
        return response

if __name__ == "__main__":
    # Start a new simulation
    sim_response = start_simulation()
    simulation_id = sim_response.id
    
    print(f"\nBase position: X={sim_response.base_pos.x}, Y={sim_response.base_pos.y}")
    print("Sensor units:")
    for unit_id, pos in sim_response.sensor_units.items():
        print(f"  Unit {unit_id}: X={pos.x}, Y={pos.y}")
    # Choose the first sensor unit
    first_sensor_id = list(sim_response.sensor_units.keys())[0]
    
    # Start controlling the first sensor unit in a separate thread
    sensor_thread = threading.Thread(
        target=control_sensor_unit,
        args=(simulation_id, first_sensor_id),
        daemon=True
    )
    sensor_thread.start()
    
    # Wait for some time to let the sensor move
    print("\nSpawning strike unit...")
    
    # Launch the strike unit
    strike_response = launch_strike_unit(simulation_id, sim_response.base_pos)
    strike_unit_id = strike_response.id
    
    # # Start controlling the strike unit in a separate thread
    # strike_thread = threading.Thread(
    #     target=control_strike_unit,
    #     args=(simulation_id, strike_unit_id),
    #     daemon=True
    # )
    # strike_thread.start()
    
    # Wait for some time to let the simulation run
    print("\nSimulation running, press Ctrl+C to exit...")
    try:
        while True:
            time.sleep(5)
            status = get_simulation_status(simulation_id)
            if hasattr(status, "status") and status.status != 0:  # Not RUNNING
                print(f"\nSimulation ended with status: {status.status}")
                break
    except KeyboardInterrupt:
        print("\nExiting...") 