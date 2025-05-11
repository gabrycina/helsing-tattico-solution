import logging
from math import sqrt
from google.protobuf.wrappers_pb2 import StringValue
from google.protobuf import any_pb2
import simulation_pb2

def get_arch_centre(direction, distance, x, y):
    directions = {
        "north":(0,1),
        "south":(0,-1),
        "east":(1,0),
        "west":(-1,0),
        "northeast":(sqrt(2)/2,sqrt(2)/2),
        "northwest":(-sqrt(2)/2,sqrt(2)/2),
        "southeast":(sqrt(2)/2,-sqrt(2)/2),
        "southwest":(-sqrt(2)/2,-sqrt(2)/2)
    }

    d = directions[direction]
    
    return (x+d[0]*distance, y+d[1]*distance)

def get_arch_x_arch_y_from_message(response):
    if response.messages:
        for msg in response.messages:
            if msg.HasField("value"):
                # Handle packed messages properly by extracting content
                if hasattr(msg.value, "value") and isinstance(msg.value.value, str):
                    msg_str = msg.value.value
                else:
                    if hasattr(msg.value, "value") and hasattr(msg.value.value, "value"):
                        # Handle binary encoded StringValue
                        if isinstance(msg.value.value.value, bytes):
                            string_value = StringValue()
                            string_value.ParseFromString(msg.value.value.value)
                            msg_str = string_value.value
                        else:
                            # This handles nested value fields
                            msg_str = msg.value.value.value
                    else:
                        # Try to unpack as StringValue
                        string_value = StringValue()
                        if hasattr(msg.value, "Unpack"):
                            msg.value.Unpack(string_value)
                            msg_str = string_value.value
                        else:
                            logging.info(f"{msg_str} AAAAAA")
                            return (None, None, None)
                         
                return map(float, msg_str.split())
    
    return (None, None, None)

def send_redundant_impulse(impulse, logger=None, unit_id=None, redundancy=1):
    """
    Generate multiple redundant impulse commands to handle connectivity issues.
    
    Args:
        impulse: The Vector2 impulse to send
        logger: Optional logger to log details
        unit_id: Optional unit ID for logging
        redundancy: Number of redundant commands to yield
        
    Yields:
        Multiple redundant UnitCommand objects with the same impulse
    """
    if logger:
        logger.info(f"Sending redundant impulse: {impulse.x}, {impulse.y} for unit {unit_id} ({redundancy}x)")
    
    # Create the command with the impulse
    command = simulation_pb2.UnitCommand(
        thrust=simulation_pb2.UnitCommand.ThrustCommand(
            impulse=impulse
        )
    )
    
    # Yield the command multiple times for redundancy
    for i in range(redundancy):
        yield command

def send_redundant_message(message_content, logger=None, unit_id=None, redundancy=3):
    """
    Generate multiple redundant message commands to handle connectivity issues.
    
    Args:
        message_content: The message string to send
        logger: Optional logger to log details
        unit_id: Optional unit ID for logging
        redundancy: Number of redundant commands to yield
        
    Yields:
        Multiple redundant UnitCommand objects with the same message
    """
    if logger:
        logger.info(f"Sending redundant message: '{message_content}' from unit {unit_id} ({redundancy}x)")
    
    # Create the StringValue and pack it into Any
    string_value = StringValue(value=message_content)
    any_message = any_pb2.Any()
    any_message.Pack(string_value)
    
    # Create the command with the message
    command = simulation_pb2.UnitCommand(
        msg=simulation_pb2.UnitCommand.MsgCommand(msg=any_message)
    )
    
    # Yield the command multiple times for redundancy
    for i in range(redundancy):
        yield command
                