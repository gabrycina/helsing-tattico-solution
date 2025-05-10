import grpc
import simulation_pb2
import simulation_pb2_grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.wrappers_pb2 import StringValue
import os
from dotenv import load_dotenv


load_dotenv()

# Server address and port
SERVER_ADDRESS = "172.237.124.96:21234"
TOKEN = os.environ["token"]


def start_simulation():
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)

        response = stub.Start(Empty(), metadata=[("authorization", f"bearer {TOKEN}")])
        print("Simulation started with parameters:")
        print(response)
        return response


def get_simulation_status(simulation_id):
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)

        request = StringValue(value=simulation_id)
        response = stub.GetSimulationStatus(
            request, metadata=[("authorization", f"bearer {TOKEN}")]
        )
        print("Simulation status:")
        print(response)


if __name__ == "__main__":
    response = start_simulation()
    # Extract the simulation ID from the response and use it
    simulation_id = response.id
    get_simulation_status(simulation_id)
