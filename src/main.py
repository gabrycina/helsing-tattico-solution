import grpc
import simulation_pb2
import simulation_pb2_grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.wrappers_pb2 import StringValue

# Server address and port
SERVER_ADDRESS = "172.237.124.96:21234"
TOKEN = "123454"

def start_simulation():
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)
        
        response = stub.Start(Empty(), metadata=[("authorization", f"bearer {TOKEN}")])
        print("Simulation started with parameters:")
        print(response)

def get_simulation_status(simulation_id):
    with grpc.insecure_channel(SERVER_ADDRESS) as channel:
        stub = simulation_pb2_grpc.SimulationStub(channel)
        
        request = StringValue(value=simulation_id)
        response = stub.GetSimulationStatus(request)
        print("Simulation status:")
        print(response)

if __name__ == "__main__":
    start_simulation()
    get_simulation_status("your_simulation_id")