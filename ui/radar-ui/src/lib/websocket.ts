"use client";

import { useEffect, useRef, useState, useCallback } from 'react';

// Define the types for our radar data
export interface RadarData {
  units: {
    id: string;
    position: { x: number; y: number };
    color?: string;
  }[];
  targets: {
    position: { x: number; y: number };
    confidence?: number;
    unitId?: string;
    unitPosition?: { x: number; y: number };
  }[];
  basePosition: { x: number; y: number };
  successMessage: string | null;
  timestamp?: number;
}

// Custom hook for WebSocket connection with improved performance
export function useRadarSocket(url: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [radarData, setRadarData] = useState<RadarData>({
    units: [],
    targets: [],
    basePosition: { x: 0, y: 0 },
    successMessage: null,
  });
  
  // Use refs to avoid re-renders and for real-time data access
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastMessageTimeRef = useRef<number>(Date.now());
  const dataRef = useRef<RadarData>(radarData);
  const pendingUpdateRef = useRef<boolean>(false);
  const updateFrameRef = useRef<number | null>(null);
  
  // Optimized data update function using requestAnimationFrame
  const processUpdate = useCallback((newData: RadarData) => {
    // Update our ref immediately with a deep clone to ensure data isolation
    if (newData.targets && newData.targets.length > 0) {
      // Log target updates for debugging
      console.log(`WS: New target data received (${newData.targets.length} targets)`);
      
      // Ensure we're getting new positions by creating fresh objects
      const freshTargets = newData.targets.map(target => ({
        position: { 
          x: Number(target.position.x), 
          y: Number(target.position.y) 
        },
        confidence: target.confidence ? Number(target.confidence) : 0.5,
        unitId: target.unitId,
        unitPosition: target.unitPosition ? { ...target.unitPosition } : undefined
      }));
      
      dataRef.current = {
        ...newData,
        targets: freshTargets,
        timestamp: Date.now()  // Add a timestamp to force updates
      };
    } else {
      dataRef.current = {
        ...newData,
        timestamp: Date.now()
      };
    }
    
    // Schedule a render update if not already pending
    if (!pendingUpdateRef.current) {
      pendingUpdateRef.current = true;
      
      // Use requestAnimationFrame for better performance
      updateFrameRef.current = requestAnimationFrame(() => {
        // Force a deep copy of the data to ensure React detects the change
        const dataCopy = JSON.parse(JSON.stringify(dataRef.current));
        setRadarData(dataCopy);
        pendingUpdateRef.current = false;
        updateFrameRef.current = null;
      });
    }
  }, []);

  // Optimized connect function
  const connect = useCallback(() => {
    // Clear any existing reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Close existing socket if it exists
    if (socketRef.current) {
      socketRef.current.close();
    }

    // Create WebSocket connection
    const socket = new WebSocket(url);
    socket.binaryType = 'arraybuffer'; // Use binary for better performance if server supports it
    socketRef.current = socket;

    // Connection opened
    socket.addEventListener('open', () => {
      console.log('WebSocket connection established');
      setIsConnected(true);
      lastMessageTimeRef.current = Date.now();
    });

    // Listen for messages - optimized handler
    socket.addEventListener('message', (event) => {
      lastMessageTimeRef.current = Date.now();
      try {
        const data = JSON.parse(event.data);
        processUpdate(data);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    });

    // Connection closed
    socket.addEventListener('close', () => {
      setIsConnected(false);
      scheduleReconnect();
    });

    // Connection error
    socket.addEventListener('error', () => {
      setIsConnected(false);
    });
  }, [url, processUpdate]);

  // Schedule reconnection with exponential backoff
  const scheduleReconnect = useCallback(() => {
    if (!reconnectTimeoutRef.current) {
      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, 200); // Faster reconnect (200ms instead of 1000ms)
    }
  }, [connect]);

  // Check for stale connections periodically
  useEffect(() => {
    const healthCheckInterval = setInterval(() => {
      const now = Date.now();
      const lastMessageAge = now - lastMessageTimeRef.current;
      
      // If no message for 2 seconds (reduced from 5s) and socket is supposedly open, try to reconnect
      if (lastMessageAge > 2000 && isConnected) {
        console.log('No messages received for 2 seconds, reconnecting...');
        connect();
      }
    }, 1000); // Check every 1 second instead of 5

    return () => {
      clearInterval(healthCheckInterval);
    };
  }, [url, isConnected, connect]);

  // Initial connection & reconnect on URL change
  useEffect(() => {
    connect();

    // Clean up on unmount
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (socketRef.current) {
        socketRef.current.close();
      }
      if (updateFrameRef.current) {
        cancelAnimationFrame(updateFrameRef.current);
      }
    };
  }, [url, connect]);

  // Function to send a message to the server
  const sendMessage = useCallback((message: any) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    }
  }, []);

  return { isConnected, radarData, sendMessage };
}

// Mock data generator for testing without actual WebSocket
export function useMockRadarData() {
  const [radarData, setRadarData] = useState<RadarData>({
    units: [
      { id: '1', position: { x: 50, y: 50 } },
      { id: '2', position: { x: -50, y: 50 } },
      { id: '3', position: { x: -50, y: -50 } },
      { id: '4', position: { x: 50, y: -50 } },
      { id: '24', position: { x: 10, y: 20 }, color: '#f7059f' },
    ],
    targets: [
      { 
        position: { x: 100, y: 120 },
        confidence: 0.8,
        unitId: '1',
        unitPosition: { x: 50, y: 50 }
      },
      { 
        position: { x: -80, y: 150 },
        confidence: 0.6,
        unitId: '2',
        unitPosition: { x: -50, y: 50 }
      },
    ],
    basePosition: { x: 0, y: 0 },
    successMessage: null,
  });

  // Update mock data periodically to simulate movement
  useEffect(() => {
    const timer = setInterval(() => {
      setRadarData(prev => {
        // Move units randomly
        const units = prev.units.map(unit => ({
          ...unit,
          position: {
            x: unit.position.x + (Math.random() * 4 - 2),
            y: unit.position.y + (Math.random() * 4 - 2),
          }
        }));

        // Move targets randomly
        const targets = prev.targets.map(target => ({
          ...target,
          position: {
            x: target.position.x + (Math.random() * 8 - 4),
            y: target.position.y + (Math.random() * 8 - 4),
          },
          // Update confidence randomly
          confidence: Math.min(1, Math.max(0.2, (target.confidence || 0.5) + (Math.random() * 0.1 - 0.05))),
        }));

        // Occasionally add/remove targets
        if (Math.random() > 0.95 && targets.length < 5) {
          const unitIndex = Math.floor(Math.random() * units.length);
          const unitPos = units[unitIndex].position;
          targets.push({
            position: {
              x: unitPos.x + (Math.random() * 200 - 100),
              y: unitPos.y + (Math.random() * 200 - 100),
            },
            confidence: 0.3 + Math.random() * 0.3,
            unitId: units[unitIndex].id,
            unitPosition: { ...unitPos },
          });
        } else if (Math.random() > 0.98 && targets.length > 2) {
          targets.pop();
        }

        return {
          ...prev,
          units,
          targets,
          // Show success message randomly
          successMessage: Math.random() > 0.99 ? "Mission Accomplished!" : prev.successMessage,
        };
      });
    }, 100);

    return () => clearInterval(timer);
  }, []);

  return { isConnected: true, radarData, sendMessage: () => {} };
} 