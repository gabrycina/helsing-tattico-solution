from math import sqrt
from google.protobuf.wrappers_pb2 import StringValue

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
                            return (None, None)
                         
                return map(float, msg_str.split())
    
    return (None, None)
                