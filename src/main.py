import grpc
import simulation_pb2
import simulation_pb2_grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.wrappers_pb2 import StringValue
import os
from dotenv import load_dotenv
import time

load_dotenv()

# Server address and port
SERVER_ADDRESS = "172.237.124.96:21234"
TOKEN = os.environ["token"]


def start_simulation() -> simulation_pb2.SimulationParameters:
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)

        simulation_parameters = stub.Start(
            Empty(), metadata=[("authorization", f"bearer {TOKEN}")]
        )
        print("Simulation started with parameters:")
        return simulation_parameters


def get_simulation_status(simulation_id: str) -> None:
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)

        request = StringValue(value=simulation_id)
        response = stub.GetSimulationStatus(
            request, metadata=[("authorization", f"bearer {TOKEN}")]
        )
        print("Simulation status:")
        print(response.status)

def check_detection(detections):
    result = []
    for direction in ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]:
        if detections.HasField(direction):
            detection: simulation_pb2.Detection = getattr(detections, direction)
            detection_class = "OBSTACLE" if getattr(detection, "class") == 0 else "TARGET"
            detection_distance = detection.distance
            result.append((direction, detection_class, detection_distance))
    return result


def unit_control(
    simulation_id: str,
    unit_id: int,
    impulse_vector: tuple[int, int],
) -> None:
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)

        # Metadata for authentication and unit identification
        metadata = [
            ("authorization", f"bearer {TOKEN}"),
            ("x-simulation-id", simulation_id),
            ("x-unit-id", str(unit_id)),
        ]

        # Generator function to send commands
        request = iter(
            [
                simulation_pb2.UnitCommand(
                    thrust=simulation_pb2.UnitCommand.ThrustCommand(
                        impulse=simulation_pb2.Vector2(
                            x=impulse_vector[0], y=impulse_vector[1]
                        )
                    )
                )
            ]
        )

        # Bidirectional streaming RPC
        responses = stub.UnitControl(request, metadata=metadata)

        # Process responses from the server
        for response in responses:
            print(response.pos.x, response.pos.y)
            print(check_detection(response.detections))
            time.sleep(3)

if __name__ == "__main__":
    simulation_parameters = start_simulation()
    print(repr(simulation_parameters))
    get_simulation_status(simulation_parameters.id)
    unit_control(simulation_parameters.id, 1, (1000, 0))
