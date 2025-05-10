import math
import logging
from typing import Dict, Any, Tuple
import simulation_pb2

logger = logging.getLogger("navigation")

class PIDController:
    """
    A simple PID controller for smooth navigation.
    """
    def __init__(self, kp=0.3, ki=0.0, kd=0.15):
        self.kp = kp  # Proportional gain
        self.ki = ki  # Integral gain
        self.kd = kd  # Derivative gain
        self.prev_error = 0.0
        self.integral = 0.0
        
    def compute(self, error: float, dt: float = 1.0) -> float:
        """
        Compute the control output based on the error.
        
        Args:
            error: The current error (distance to target)
            dt: Time step (default 1.0 because we're using simulation ticks)
            
        Returns:
            The control output
        """
        # Proportional term
        p_term = self.kp * error
        
        # Integral term
        self.integral += error * dt
        i_term = self.ki * self.integral
        
        # Derivative term
        d_term = self.kd * (error - self.prev_error) / dt
        self.prev_error = error
        
        return p_term + i_term + d_term

class UnitNavigator:
    """
    Navigation system for a single unit, handling inertia.
    """
    def __init__(self):
        # Initialize unit state
        self.last_pos = None
        self.estimated_velocity = (0, 0)
        self.target_pos = None
        self.pid_x = PIDController()
        self.pid_y = PIDController()
        self.arrival_threshold = 0.1
        self.max_impulse = 10.0  # Increased to allow larger impulses (up to 10)
    
    def update_position(self, current_pos: Tuple[float, float]):
        """
        Update the position tracking
        
        Args:
            current_pos: The current position (x, y)
        """
        # If we have a previous position, estimate velocity
        if self.last_pos is not None:
            prev_x, prev_y = self.last_pos
            curr_x, curr_y = current_pos
            
            # Estimate velocity (units per tick)
            vx = curr_x - prev_x
            vy = curr_y - prev_y
            self.estimated_velocity = (vx*250, vy*250)
        
        # Update last position
        self.last_pos = current_pos
    
    def set_target(self, target_pos: Tuple[float, float]):
        """
        Set a target position
        
        Args:
            target_pos: The target position (x, y)
        """
        # Only reset controllers if target changes
        if self.target_pos != target_pos:
            self.target_pos = target_pos
            # Reset PID controllers when target changes
            self.pid_x = PIDController()
            self.pid_y = PIDController()
    
    def get_navigation_impulse(self) -> simulation_pb2.Vector2:
        """
        Calculate the impulse needed to navigate to the target point.
        
        Returns:
            Vector2 with the impulse to apply
        """
        if self.target_pos is None or self.last_pos is None:
            # No target or no position data, return zero impulse
            return simulation_pb2.Vector2(x=0.0, y=0.0)
        
        current_x, current_y = self.last_pos
        target_x, target_y = self.target_pos
        
        # Calculate distance to target
        dx = target_x - current_x
        dy = target_y - current_y
        distance = math.sqrt(dx*dx + dy*dy)
        
        # Check if we've arrived at the target
        if distance < self.arrival_threshold:
            # We've arrived, apply breaking force to counter current velocity
            vx, vy = self.estimated_velocity
            breaking_x = -vx
            breaking_y = -vy
            
            logger.debug(f"Arrived at target. Applying breaking force: ({breaking_x:.2f}, {breaking_y:.2f})")
            return simulation_pb2.Vector2(x=breaking_x, y=breaking_y)
        
        # Compute PID control for each axis
        control_x = self.pid_x.compute(dx)
        control_y = self.pid_y.compute(dy)
        
        # Factor in velocity damping (to counteract current velocity)
        vx, vy = self.estimated_velocity
        
        # Calculate distance-based damping factor
        # Apply more damping as we get closer to target
        base_damping = 0.2  # Reduced base damping for higher impulses
        proximity_factor = max(0, 1.0 - (distance / 15.0))  # Adjusted distance scale for larger movements
        damping_factor = base_damping + (proximity_factor * 0.8)  # Up to 1.0 at target
        
        # Apply damping to counter momentum
        impulse_x = control_x - (vx * damping_factor)
        impulse_y = control_y - (vy * damping_factor)
        
        # Normalize if the impulse exceeds maximum
        impulse_magnitude = math.sqrt(impulse_x*impulse_x + impulse_y*impulse_y)
        max_impulse = self.max_impulse
        if impulse_magnitude > max_impulse:
            scale_factor = max_impulse / impulse_magnitude
            impulse_x *= scale_factor
            impulse_y *= scale_factor
        
        logger.debug(f"Navigation: dist={distance:.2f}, impulse=({impulse_x:.2f}, {impulse_y:.2f})")
        return simulation_pb2.Vector2(x=impulse_x, y=impulse_y)

    def is_at_target(self, arrival_threshold=None) -> bool:
        """Check if unit has reached its target"""
        if self.target_pos is None or self.last_pos is None:
            return False
        
        arrival_threshold = arrival_threshold or self.arrival_threshold
        
        current_x, current_y = self.last_pos
        target_x, target_y = self.target_pos
        
        dx = target_x - current_x
        dy = target_y - current_y
        distance = math.sqrt(dx*dx + dy*dy)
        
        return distance < arrival_threshold

def navigate_to_point(navigator: UnitNavigator, 
                     current_pos: Tuple[float, float], 
                     target_pos: Tuple[float, float]) -> simulation_pb2.Vector2:
    """
    High-level function to generate an impulse to navigate to a point.
    
    Args:
        navigator: The unit's navigator instance
        current_pos: Current position (x, y)
        target_pos: Target position (x, y)
        
    Returns:
        Vector2 with the impulse to apply
    """
    # Update the navigator with current position
    navigator.update_position(current_pos)
    
    # Set the target position
    navigator.set_target(target_pos)
    
    # Get the navigation impulse
    return navigator.get_navigation_impulse()

def navigate_to_direction(navigator: UnitNavigator, 
                         current_pos: Tuple[float, float], 
                         direction: str, 
                         distance: float = 10.0) -> simulation_pb2.Vector2:
    """
    Navigate in a specific cardinal direction.
    
    Args:
        navigator: The unit's navigator instance
        current_pos: Current position (x, y)
        direction: Cardinal direction ('north', 'northeast', etc.)
        distance: How far to go in that direction
        
    Returns:
        Vector2 with the impulse to apply
    """
    # Convert direction to target position
    current_x, current_y = current_pos
    
    # Direction vectors for each cardinal direction
    direction_vectors = {
        "north": (0, 1),
        "northeast": (0.7071, 0.7071),
        "east": (1, 0),
        "southeast": (0.7071, -0.7071),
        "south": (0, -1),
        "southwest": (-0.7071, -0.7071),
        "west": (-1, 0),
        "northwest": (-0.7071, 0.7071)
    }
    
    if direction not in direction_vectors:
        # Invalid direction, default to east
        dx, dy = (1, 0)
    else:
        dx, dy = direction_vectors[direction]
    
    # Calculate target position
    target_x = current_x + (dx * distance)
    target_y = current_y + (dy * distance)
    
    return navigate_to_point(navigator, current_pos, (target_x, target_y)) 