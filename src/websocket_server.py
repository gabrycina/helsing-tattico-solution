"""
WebSocket server for Helsing tactical radar UI

Provides real-time updates of the radar display to the UI.
"""

import asyncio
import json
import logging
import websockets
import time
import threading
from typing import Set, Dict, Any, Optional

# Configure module logger
logger = logging.getLogger("websocket")

class RadarWebSocketServer:
    """WebSocket server to provide real-time radar updates to the UI"""

    def __init__(self, host: str = "localhost", port: int = 8765, radar=None):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.radar_data: Dict[str, Any] = {
            "units": [],
            "targets": [],
            "basePosition": {"x": 0, "y": 0},
            "successMessage": None
        }
        self.server = None
        self.running = False
        self.radar = radar
        self.update_thread = None
        logger.info(f"WebSocket server initialized on {host}:{port}")

    async def register(self, websocket: websockets.WebSocketServerProtocol):
        """Register a new client connection"""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")
        
        # Send current state to the new client
        await self.send_to_client(websocket, self.radar_data)

    async def unregister(self, websocket: websockets.WebSocketServerProtocol):
        """Unregister a client connection"""
        self.clients.remove(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.clients)}")

    async def handle_connection(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Handle a client connection"""
        await self.register(websocket)
        try:
            async for message in websocket:
                # Handle any messages from clients
                try:
                    data = json.loads(message)
                    logger.debug(f"Received message: {data}")
                    # Currently, we don't expect any client messages
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON: {message}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed")
        finally:
            await self.unregister(websocket)

    async def broadcast(self, data: Dict[str, Any]):
        """Broadcast data to all connected clients"""
        if not self.clients:
            return
        
        tasks = [self.send_to_client(client, data) for client in self.clients]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def send_to_client(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """Send data to a specific client"""
        try:
            await websocket.send(json.dumps(data))
        except websockets.exceptions.ConnectionClosed:
            logger.debug("Failed to send - connection closed")
        except Exception as e:
            logger.error(f"Error sending to client: {e}")

    def update_units(self, units: list):
        """Update the units data"""
        self.radar_data["units"] = units
        asyncio.create_task(self.broadcast(self.radar_data))

    def update_targets(self, targets: list):
        """Update the targets data"""
        self.radar_data["targets"] = targets
        asyncio.create_task(self.broadcast(self.radar_data))

    def set_base_position(self, x: float, y: float):
        """Set the base position"""
        self.radar_data["basePosition"] = {"x": x, "y": y}
        asyncio.create_task(self.broadcast(self.radar_data))

    def set_success_message(self, message: Optional[str] = None):
        """Set the success message"""
        self.radar_data["successMessage"] = message
        asyncio.create_task(self.broadcast(self.radar_data))

    def update_all(self, units: list, targets: list, base_position: Dict[str, float], success_message: Optional[str] = None):
        """Update all radar data at once"""
        self.radar_data = {
            "units": units,
            "targets": targets,
            "basePosition": base_position,
            "successMessage": success_message,
            "timestamp": time.time()  # Add timestamp to ensure each update is unique
        }
        asyncio.create_task(self.broadcast(self.radar_data))

    def update_from_radar(self):
        """Update data from the connected radar instance"""
        if not self.radar:
            return
            
        # Log current radar state for debugging
        logger.debug(f"Updating from radar. Units: {len(self.radar.units)}, Targets: {len(self.radar.radar_targets)}")

        # Transform units from radar to WebSocket format
        ws_units = []
        for unit_id, (x, y, color) in self.radar.units.items():
            # Determine if this is a strike unit by color
            unit_type = "sensor"
            if color == (255, 0, 255) or color == (255, 0, 255, 255):  # This is a common color for strike units
                unit_type = "strike"
            elif color == (0, 255, 0) or color == (0, 255, 0, 255):  # Common color for base
                unit_type = "base"
                
            ws_units.append({
                "id": unit_id,
                "position": {"x": float(x), "y": float(y)},
                "type": unit_type
            })
            
            logger.debug(f"Unit {unit_id}: pos=({x}, {y}), type={unit_type}")
        
        # Get targets information if available
        ws_targets = []
        if hasattr(self.radar, "radar_targets") and self.radar.radar_targets:
            for i, target in enumerate(self.radar.radar_targets):
                if len(target) >= 2:  # Must have at least x and y
                    target_data = {
                        "position": {"x": float(target[0]), "y": float(target[1])}
                    }
                    if len(target) > 2:  # If confidence is available
                        target_data["confidence"] = float(target[2])
                    else:
                        target_data["confidence"] = 0.8  # Default confidence
                        
                    ws_targets.append(target_data)
                    logger.debug(f"Target {i}: pos=({target[0]}, {target[1]}), conf={target_data.get('confidence', 'N/A')}")
        
        # Get base position
        base_pos = {"x": 0, "y": 0}
        if hasattr(self.radar, "base_position") and self.radar.base_position:
            base_pos = {"x": float(self.radar.base_position[0]), "y": float(self.radar.base_position[1])}
            logger.debug(f"Base position: ({base_pos['x']}, {base_pos['y']})")
        
        # Check for success message
        success_msg = None
        if hasattr(self.radar, "running") and not self.radar.running.is_set():
            success_msg = "Mission Accomplished!"
            logger.debug("Success state detected")
        
        # Update all data - always send an update to keep the connection active
        # Add a timestamp to ensure each update is unique
        self.update_all(ws_units, ws_targets, base_pos, success_msg)
        logger.debug(f"Updated WebSocket data with {len(ws_units)} units and {len(ws_targets)} targets")

    def start_update_thread(self):
        """Start a thread to periodically update data from radar"""
        if self.radar:
            def update_loop():
                logger.info("Starting WebSocket update loop")
                try:
                    last_update_time = 0
                    min_update_interval = 0.02  # Reduced to 20ms (from 100ms)
                    heartbeat_interval = 1.0   # Send heartbeat every 1 second even if no changes
                    
                    while self.running:
                        try:
                            current_time = time.time()
                            time_since_last_update = current_time - last_update_time
                            
                            # Update at least every heartbeat_interval to keep connection alive
                            if time_since_last_update >= min_update_interval:
                                self.update_from_radar()
                                last_update_time = current_time
                                
                            # Sleep for a smaller amount to minimize CPU usage while allowing faster updates
                            time.sleep(0.005)  # Reduced from 0.05s to 0.005s
                                
                        except Exception as e:
                            logger.error(f"Error in update loop: {e}")
                            time.sleep(0.1)  # Reduced from 0.5s to 0.1s on error
                except Exception as e:
                    logger.error(f"WebSocket update thread crashed: {e}")
                finally:
                    logger.info("WebSocket update loop stopped")
            
            self.update_thread = threading.Thread(target=update_loop, daemon=True)
            # Increase thread priority if possible
            if hasattr(self.update_thread, "priority"):
                self.update_thread.priority = 1  # Higher priority
            self.update_thread.start()
            logger.info("WebSocket update thread started with 20ms update interval")

    async def start(self):
        """Start the WebSocket server"""
        self.running = True
        self.server = await websockets.serve(self.handle_connection, self.host, self.port)
        
        # Start radar update thread if we have a radar connected
        if self.radar:
            self.start_update_thread()
            
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
        return self.server

    async def stop(self):
        """Stop the WebSocket server"""
        if self.server:
            self.running = False
            self.server.close()
            await self.server.wait_closed()
            logger.info("WebSocket server stopped")


# When run directly, start a standalone server with example data
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Create server instance
    server = RadarWebSocketServer()
    
    # Example data for standalone testing
    example_units = [
        {"id": "1", "position": {"x": 50, "y": 50}, "type": "sensor"},
        {"id": "2", "position": {"x": -50, "y": 50}, "type": "sensor"},
        {"id": "3", "position": {"x": -50, "y": -50}, "type": "sensor"},
        {"id": "4", "position": {"x": 50, "y": -50}, "type": "strike"},
    ]
    
    example_targets = [
        {"position": {"x": 100, "y": 100}, "confidence": 0.8},
    ]
    
    # Run the server with example data
    async def main():
        await server.start()
        
        # Example usage: update data every second
        for i in range(10):
            # Move a unit
            example_units[0]["position"]["x"] += 5
            
            # Add a target with random confidence
            if i == 5:
                example_targets.append({
                    "position": {"x": -120, "y": 80},
                    "confidence": 0.6
                })
            
            # Update the server data
            server.update_all(
                example_units,
                example_targets,
                {"x": 0, "y": 0},
                "Mission Accomplished!" if i == 9 else None
            )
            
            await asyncio.sleep(1)
        
        # Wait for 5 more seconds before shutting down
        await asyncio.sleep(5)
        await server.stop()
    
    asyncio.run(main()) 