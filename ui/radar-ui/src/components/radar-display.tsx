"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";

interface Unit {
  id: string;
  position: { x: number; y: number };
  color?: string;
}

interface Target {
  position: { x: number; y: number };
  confidence?: number;
  unitId?: string;
  unitPosition?: { x: number; y: number };
}

interface RadarDisplayProps {
  width?: number;
  height?: number;
  units?: Unit[];
  targets?: Target[];
  basePosition?: { x: number; y: number };
  showGrid?: boolean;
  successMessage?: string | null;
}

export function RadarDisplay({
  width = 800,
  height = 800,
  units = [],
  targets = [],
  basePosition = { x: 0, y: 0 },
  showGrid = true,
  successMessage = null,
}: RadarDisplayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [scale, setScale] = useState(1);
  const requestIdRef = useRef<number | null>(null);
  const timerIdRef = useRef<number | null>(null);
  
  // Add a dependency to track target position changes
  const [lastTargetPosition, setLastTargetPosition] = useState<{x: number, y: number} | null>(null);
  
  // Calculate the optimal scale factor based on container size
  useEffect(() => {
    const updateScale = () => {
      if (!canvasRef.current) return;
      
      const container = canvasRef.current.parentElement;
      if (!container) return;
      
      const containerWidth = container.clientWidth;
      const containerHeight = container.clientHeight;
      
      const scaleX = containerWidth / width;
      const scaleY = containerHeight / height;
      
      setScale(Math.min(scaleX, scaleY));
    };
    
    updateScale();
    window.addEventListener('resize', updateScale);
    
    return () => window.removeEventListener('resize', updateScale);
  }, [width, height]);

  // Convert cartesian to polar coordinates
  const cartesianToPolar = (x: number, y: number) => {
    // Calculate distance from center (radius)
    const distance = Math.sqrt(x * x + y * y);
    
    // Calculate angle in radians, then convert to degrees
    // atan2 returns angle in range (-PI, PI), we convert to (0, 360)
    let angle = Math.atan2(-y, x) * (180 / Math.PI);
    if (angle < 0) angle += 360;
    
    return { distance, angle };
  };
  
  // Convert polar to cartesian coordinates
  const polarToCartesian = (radius: number, angleDegrees: number) => {
    const angleRadians = (angleDegrees * Math.PI) / 180;
    const x = radius * Math.cos(angleRadians);
    const y = -radius * Math.sin(angleRadians);
    return { x, y };
  };

  // Render the radar in a requestAnimationFrame loop to optimize performance
  const renderRadar = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d", { alpha: false, desynchronized: true });
    if (!ctx) return;

    // Clear canvas with a solid dark green background - use fast clearing
    ctx.fillStyle = "rgb(0, 15, 0)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Create background gradient
    const bgGradient = ctx.createRadialGradient(
      canvas.width/2, canvas.height/2, 0,
      canvas.width/2, canvas.height/2, canvas.width/2
    );
    bgGradient.addColorStop(0, "rgba(0, 35, 0, 1)");
    bgGradient.addColorStop(0.7, "rgba(0, 20, 0, 1)");
    bgGradient.addColorStop(1, "rgba(0, 10, 0, 1)");
    
    // Fill background
    ctx.fillStyle = bgGradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Apply global transforms for radar coordinates
    ctx.save();
    
    // Get center of canvas
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    
    // Translate origin to center of the canvas
    ctx.translate(centerX, centerY);
    
    // Calculate the size of the radar circle
    const radarRadius = Math.min(canvas.width, canvas.height) * 0.45;
    
    // Draw the main circular radar display
    ctx.beginPath();
    ctx.arc(0, 0, radarRadius, 0, Math.PI * 2);
    
    // Create circular gradient for radar display
    const radarGradient = ctx.createRadialGradient(0, 0, 0, 0, 0, radarRadius);
    radarGradient.addColorStop(0, "rgba(0, 40, 0, 0.9)");
    radarGradient.addColorStop(0.7, "rgba(0, 30, 0, 0.7)");
    radarGradient.addColorStop(1, "rgba(0, 20, 0, 0.5)");
    
    ctx.fillStyle = radarGradient;
    ctx.fill();
    
    // Draw radar circles
    for (let i = 1; i <= 5; i++) {
      const radius = (radarRadius / 5) * i;
      ctx.beginPath();
      ctx.arc(0, 0, radius, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(0, 255, 0, 0.3)";
      ctx.lineWidth = i === 5 ? 1.5 : 0.8;
      ctx.stroke();
    }
    
    // Draw degree markings around the edge
    ctx.save();
    ctx.strokeStyle = "rgba(0, 255, 0, 0.5)";
    ctx.fillStyle = "rgba(0, 255, 0, 0.7)";
    ctx.font = "16px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    
    // Draw degree ticks and labels
    for (let angle = 0; angle < 360; angle += 10) {
      const radian = (angle * Math.PI) / 180;
      const tickLength = angle % 30 === 0 ? 15 : 7;
      
      // Draw tick marks
      ctx.beginPath();
      ctx.moveTo(
        (radarRadius + 5) * Math.cos(radian),
        (radarRadius + 5) * Math.sin(radian)
      );
      ctx.lineTo(
        (radarRadius + 5 + tickLength) * Math.cos(radian),
        (radarRadius + 5 + tickLength) * Math.sin(radian)
      );
      ctx.stroke();
      
      // Draw degree numbers every 30 degrees
      if (angle % 30 === 0) {
        const labelRadius = radarRadius + 30;
        const labelX = labelRadius * Math.cos(radian);
        const labelY = labelRadius * Math.sin(radian);
        
        // Format the angle - add leading zeros to make 3 digits
        const formattedAngle = angle.toString().padStart(3, '0');
        
        // Rotate the context to align text with the circle
        ctx.save();
        ctx.translate(labelX, labelY);
        
        // Rotate text to be readable from outside
        if (angle > 90 && angle < 270) {
          ctx.rotate(radian + Math.PI);
        } else {
          ctx.rotate(radian);
        }
        
        ctx.fillText(formattedAngle, 0, 0);
        ctx.restore();
      }
    }
    
    // Add cartesian coordinate labels for reference
    ctx.fillStyle = "rgba(255, 255, 0, 0.9)";
    ctx.font = "bold 16px monospace";
    // Right (+100, 0)
    ctx.fillText("100", radarRadius - 25, 0);
    // Left (-100, 0)
    ctx.fillText("-100", -radarRadius + 25, 0);
    // Top (0, +100)
    ctx.fillText("100", 0, -radarRadius + 25);
    // Bottom (0, -100)
    ctx.fillText("-100", 0, radarRadius - 25);
    
    ctx.restore();
    
    // Draw radar sweep line
    const now = Date.now();
    const sweepAngle = (now / 50) % 360; // Full rotation every ~18 seconds
    const sweepRadian = (sweepAngle * Math.PI) / 180;
    
    // Draw sweep gradient - using a sector approach instead of conic gradient
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.arc(0, 0, radarRadius, sweepRadian - 0.4, sweepRadian, false);
    ctx.closePath();
    
    // Create radial gradient for sweep effect
    const sweepGradient = ctx.createRadialGradient(0, 0, 0, 0, 0, radarRadius);
    sweepGradient.addColorStop(0, "rgba(0, 255, 0, 0.3)");
    sweepGradient.addColorStop(0.7, "rgba(0, 255, 0, 0.15)");
    sweepGradient.addColorStop(1, "rgba(0, 255, 0, 0)");
    
    ctx.fillStyle = sweepGradient;
    ctx.fill();
    
    // Draw sweep line
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(radarRadius * Math.cos(sweepRadian), radarRadius * Math.sin(sweepRadian));
    ctx.strokeStyle = "rgba(0, 255, 0, 0.8)";
    ctx.lineWidth = 2;
    ctx.stroke();
    
    // Draw center dot
    ctx.beginPath();
    ctx.arc(0, 0, 3, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0, 255, 0, 0.8)";
    ctx.fill();
    
    // Draw units (convert to polar for radar display)
    units.forEach((unit) => {
      // Convert cartesian to polar coordinates
      const { distance, angle } = cartesianToPolar(unit.position.x, unit.position.y);
      
      // Scale distance to fit radar (assuming max coordinate is 100)
      const scaledDistance = (distance / 100) * radarRadius;
      
      // Convert back to display cartesian coordinates
      const displayX = scaledDistance * Math.cos((angle * Math.PI) / 180);
      const displayY = scaledDistance * Math.sin((angle * Math.PI) / 180);
      
      // Determine if it's a strike unit (not 1-4)
      const isStrikeUnit = !["1", "2", "3", "4"].includes(unit.id);
      
      if (isStrikeUnit) {
        // Draw bracket-style target
        const bracketSize = 30; // Reduced from 50, but still large
        
        ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
        ctx.lineWidth = 2.5; // Slightly reduced
        
        // Top-left bracket
        ctx.beginPath();
        ctx.moveTo(displayX - bracketSize, displayY - bracketSize/2);
        ctx.lineTo(displayX - bracketSize, displayY - bracketSize);
        ctx.lineTo(displayX - bracketSize/2, displayY - bracketSize);
        ctx.stroke();
        
        // Top-right bracket
        ctx.beginPath();
        ctx.moveTo(displayX + bracketSize/2, displayY - bracketSize);
        ctx.lineTo(displayX + bracketSize, displayY - bracketSize);
        ctx.lineTo(displayX + bracketSize, displayY - bracketSize/2);
        ctx.stroke();
        
        // Bottom-left bracket
        ctx.beginPath();
        ctx.moveTo(displayX - bracketSize, displayY + bracketSize/2);
        ctx.lineTo(displayX - bracketSize, displayY + bracketSize);
        ctx.lineTo(displayX - bracketSize/2, displayY + bracketSize);
        ctx.stroke();
        
        // Bottom-right bracket
        ctx.beginPath();
        ctx.moveTo(displayX + bracketSize/2, displayY + bracketSize);
        ctx.lineTo(displayX + bracketSize, displayY + bracketSize);
        ctx.lineTo(displayX + bracketSize, displayY + bracketSize/2);
        ctx.stroke();
        
        // Draw center dot in magenta - slightly smaller
        ctx.beginPath();
        ctx.arc(displayX, displayY, 12, 0, Math.PI * 2); // Reduced from 18
        ctx.fillStyle = "rgba(255, 0, 255, 1.0)";
        ctx.fill();
        
        // Add stronger glow effect
        ctx.beginPath();
        ctx.arc(displayX, displayY, 16, 0, Math.PI * 2); // Reduced from 24
        ctx.strokeStyle = "rgba(255, 100, 255, 0.8)";
        ctx.lineWidth = 2.5;
        ctx.stroke();
      } else {
        // Draw standard radar blip with glow - slightly smaller
        ctx.beginPath();
        ctx.arc(displayX, displayY, 10, 0, Math.PI * 2); // Reduced from 16
        ctx.fillStyle = "rgba(0, 255, 0, 1.0)";
        ctx.fill();
        
        // Add bright dot in center of blip
        ctx.beginPath();
        ctx.arc(displayX, displayY, 5, 0, Math.PI * 2); // Reduced from 8
        ctx.fillStyle = "rgba(200, 255, 200, 1.0)";
        ctx.fill();
        
        // Add brackets around regular units - more visible
        ctx.strokeStyle = "rgba(180, 255, 180, 0.9)";
        ctx.lineWidth = 1.5; // Slightly reduced
        
        const smallBracket = 16; // Reduced from 25
        // Draw brackets
        ctx.beginPath();
        ctx.moveTo(displayX - smallBracket, displayY - smallBracket);
        ctx.lineTo(displayX - smallBracket, displayY - smallBracket/2);
        ctx.stroke();
        
        ctx.beginPath();
        ctx.moveTo(displayX + smallBracket, displayY - smallBracket);
        ctx.lineTo(displayX + smallBracket, displayY - smallBracket/2);
        ctx.stroke();
        
        ctx.beginPath();
        ctx.moveTo(displayX - smallBracket, displayY + smallBracket);
        ctx.lineTo(displayX - smallBracket, displayY + smallBracket/2);
        ctx.stroke();
        
        ctx.beginPath();
        ctx.moveTo(displayX + smallBracket, displayY + smallBracket);
        ctx.lineTo(displayX + smallBracket, displayY + smallBracket/2);
        ctx.stroke();
      }
    });
    
    // Draw base position as special marker (yellow diamond)
    if (basePosition.x !== 0 || basePosition.y !== 0) {
      // Convert to polar coordinates
      const { distance, angle } = cartesianToPolar(basePosition.x, basePosition.y);
      
      // Scale distance
      const scaledDistance = (distance / 100) * radarRadius;
      
      // Convert back to display coordinates
      const displayX = scaledDistance * Math.cos((angle * Math.PI) / 180);
      const displayY = scaledDistance * Math.sin((angle * Math.PI) / 180);
      
      // Draw base marker (diamond shape) - slightly smaller
      const baseSize = 15; // Reduced from 20
      ctx.beginPath();
      ctx.moveTo(displayX, displayY - baseSize);
      ctx.lineTo(displayX + baseSize, displayY);
      ctx.lineTo(displayX, displayY + baseSize);
      ctx.lineTo(displayX - baseSize, displayY);
      ctx.closePath();
      
      // Create gradient for base marker - brighter yellow
      const baseGradient = ctx.createRadialGradient(
        displayX, displayY, 0,
        displayX, displayY, baseSize * 1.2
      );
      baseGradient.addColorStop(0, "rgba(255, 255, 0, 1.0)");
      baseGradient.addColorStop(0.7, "rgba(255, 200, 0, 0.9)");
      baseGradient.addColorStop(1, "rgba(255, 150, 0, 0.7)");
      
      ctx.fillStyle = baseGradient;
      ctx.fill();
      
      // Add pulsing effect to make it more noticeable
      const pulseSize = baseSize * (1 + 0.2 * Math.sin(Date.now() / 300));
      ctx.beginPath();
      ctx.moveTo(displayX, displayY - pulseSize);
      ctx.lineTo(displayX + pulseSize, displayY);
      ctx.lineTo(displayX, displayY + pulseSize);
      ctx.lineTo(displayX - pulseSize, displayY);
      ctx.closePath();
      
      ctx.strokeStyle = "rgba(255, 255, 0, 0.8)";
      ctx.lineWidth = 2.5;
      ctx.stroke();
      
      // Add "BASE" label near the marker for clarity
      ctx.fillStyle = "rgba(255, 255, 0, 1.0)";
      ctx.font = "bold 12px monospace";
      ctx.textAlign = "center";
      ctx.fillText("BASE", displayX, displayY + baseSize + 18);
    }

    // Draw mission accomplished overlay if needed
    if (successMessage) {
      // Create full-screen semi-transparent overlay
      ctx.fillStyle = "rgba(0, 0, 0, 0.7)";
      ctx.fillRect(-canvas.width/2, -canvas.height/2, canvas.width, canvas.height);
      
      // Draw animated success indicator
      const pulseScale = 1 + 0.05 * Math.sin(Date.now() / 300);
      
      // Success message box
      const msgBoxWidth = radarRadius * 1.2;
      const msgBoxHeight = radarRadius * 0.4;
      
      ctx.save();
      ctx.scale(pulseScale, pulseScale);
      
      // Create gradient for message box
      const msgGradient = ctx.createLinearGradient(
        -msgBoxWidth/2, 0,
        msgBoxWidth/2, 0
      );
      msgGradient.addColorStop(0, "rgba(0, 60, 0, 0.9)");
      msgGradient.addColorStop(0.5, "rgba(0, 100, 0, 0.9)");
      msgGradient.addColorStop(1, "rgba(0, 60, 0, 0.9)");
      
      // Draw message box
      ctx.fillStyle = msgGradient;
      roundedRect(
        ctx,
        -msgBoxWidth/2,
        -msgBoxHeight/2,
        msgBoxWidth,
        msgBoxHeight,
        10
      );
      ctx.fill();
      
      // Add border
      ctx.strokeStyle = "rgba(0, 255, 0, 0.8)";
      ctx.lineWidth = 2;
      ctx.stroke();
      
      // Draw text
      ctx.fillStyle = "rgba(0, 255, 0, 1)";
      ctx.font = "bold 24px monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.shadowColor = "rgba(0, 255, 0, 1)";
      ctx.shadowBlur = 10;
      
      // Split message if needed
      const words = successMessage.split(" ");
      if (words.length > 3) {
        const firstHalf = words.slice(0, words.length/2).join(" ");
        const secondHalf = words.slice(words.length/2).join(" ");
        
        ctx.fillText(firstHalf, 0, -15);
        ctx.fillText(secondHalf, 0, 15);
      } else {
        ctx.fillText(successMessage, 0, 0);
      }
      
      ctx.restore();
    }
    
    // Draw targets as red triangles - show only THE most recent position
    if (targets && targets.length > 0) {
      // Find the single most recent target with highest confidence
      // Reset most recent target on each frame to ensure proper updates
      let mostRecentTarget = targets[targets.length - 1]; // Start with the latest received target
      
      // Find the target with the highest confidence value (only if confidence exists)
      let highestConfidence = mostRecentTarget.confidence || 0;
      
      targets.forEach(target => {
        const targetConfidence = target.confidence || 0;
        // Prioritize targets with higher confidence
        if (targetConfidence > highestConfidence) {
          highestConfidence = targetConfidence;
          mostRecentTarget = target;
        }
      });
      
      // Log target position for debugging
      console.log(`Displaying target at x:${mostRecentTarget.position.x.toFixed(2)}, y:${mostRecentTarget.position.y.toFixed(2)}, conf:${highestConfidence.toFixed(2)}`);
      
      // Draw only the single most recent target
      // Convert cartesian to polar coordinates
      const { distance, angle } = cartesianToPolar(mostRecentTarget.position.x, mostRecentTarget.position.y);
      
      // Scale distance to fit radar
      const scaledDistance = (distance / 100) * radarRadius;
      
      // Convert back to display cartesian coordinates
      const displayX = scaledDistance * Math.cos((angle * Math.PI) / 180);
      const displayY = scaledDistance * Math.sin((angle * Math.PI) / 180);
      
      // Draw target as a red triangle
      const triangleSize = 18; // Make it larger since it's the only one
      ctx.beginPath();
      // Triangle pointing up
      ctx.moveTo(displayX, displayY - triangleSize);
      ctx.lineTo(displayX + triangleSize, displayY + triangleSize);
      ctx.lineTo(displayX - triangleSize, displayY + triangleSize);
      ctx.closePath();
      
      // Create gradient for target
      const targetGradient = ctx.createLinearGradient(
        displayX, displayY - triangleSize,
        displayX, displayY + triangleSize
      );
      targetGradient.addColorStop(0, "rgba(255, 50, 50, 1.0)");
      targetGradient.addColorStop(1, "rgba(200, 0, 0, 0.9)");
      
      ctx.fillStyle = targetGradient;
      ctx.fill();
      
      // Add border
      ctx.strokeStyle = "rgba(255, 180, 180, 0.8)";
      ctx.lineWidth = 2;
      ctx.stroke();
      
      // Add PRIORITY TARGET label
      ctx.fillStyle = "rgba(255, 0, 0, 1.0)";
      ctx.font = "bold 14px monospace";
      ctx.textAlign = "center";
      ctx.fillText("PRIORITY TARGET", displayX, displayY + triangleSize + 18);
      
      // Add pulsing effect - more pronounced
      const pulseSize = triangleSize * (1 + 0.3 * Math.sin(Date.now() / 200));
      ctx.beginPath();
      ctx.moveTo(displayX, displayY - pulseSize);
      ctx.lineTo(displayX + pulseSize, displayY + pulseSize);
      ctx.lineTo(displayX - pulseSize, displayY + pulseSize);
      ctx.closePath();
      ctx.strokeStyle = "rgba(255, 0, 0, 0.6)";
      ctx.lineWidth = 2;
      ctx.stroke();
      
      // Add target distance and heading
      ctx.fillStyle = "rgba(255, 255, 0, 0.9)";
      ctx.font = "bold 12px monospace";
      ctx.fillText(`DIST: ${Math.round(distance)}`, displayX, displayY - triangleSize - 10);
      ctx.fillText(`HDG: ${Math.round(angle)}°`, displayX, displayY - triangleSize - 25);
    }
    
    ctx.restore(); // Restore the context state
  }, [width, height, units, basePosition, successMessage, targets]);

  // Helper function for drawing rounded rectangles
  function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
  }

  // Set up high-frequency animation loop with performance optimization
  useEffect(() => {  
    // Use a more efficient rendering approach
    let lastRenderTime = 0;
    const targetInterval = 10; // Target 10ms between frames (~100fps)
    let animationId: number;
    
    const render = (timestamp: number) => {
      const elapsed = timestamp - lastRenderTime;
      
      if (elapsed >= targetInterval) {
        lastRenderTime = timestamp;
        renderRadar();
      }
      
      animationId = requestAnimationFrame(render);
    };
    
    // Start the animation loop
    animationId = requestAnimationFrame(render);
    
    // Clean up
    return () => {
      cancelAnimationFrame(animationId);
      if (timerIdRef.current) {
        clearTimeout(timerIdRef.current);
      }
    };
  }, [renderRadar]);
  
  // Add another effect for immediate rendering on data changes
  useEffect(() => {
    // Force an immediate render when units or targets change
    renderRadar();
  }, [units, targets, basePosition, renderRadar]);

  // Optimize throttling for better performance
  useEffect(() => {
    let lastUpdate = 0;
    const throttleDuration = 5; // Reduced throttle duration for more responsive updates
    
    const handleUnitsUpdate = () => {
      const now = performance.now(); // Use performance.now() for more accurate timing
      if (now - lastUpdate > throttleDuration) {
        lastUpdate = now;
        // Force immediate render on data change
        renderRadar();
      }
    };
    
    handleUnitsUpdate();
    
    return () => {
      // Cleanup
    };
  }, [units, targets, basePosition, renderRadar]);

  // Set canvas size with optimized settings
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const updateCanvasSize = () => {
      // Get the window dimensions for fullscreen
      const parentWidth = window.innerWidth;
      const parentHeight = window.innerHeight;
      
      // Set display size to fill screen completely
      canvas.style.width = `${parentWidth}px`;
      canvas.style.height = `${parentHeight}px`;
      
      // Calculate a new scale based on the actual dimensions
      const newScaleX = parentWidth / width;
      const newScaleY = parentHeight / height;
      setScale(Math.min(newScaleX, newScaleY));
      
      // Set actual size in memory (scaled to account for extra pixel density)
      // but limit max resolution for performance
      const dpr = Math.min(window.devicePixelRatio || 1, 2); // Cap DPR at 2 for performance
      canvas.width = parentWidth * dpr;
      canvas.height = parentHeight * dpr;
    };
    
    // Initial update
    updateCanvasSize();
    
    // Use optimized resize handler
    let resizeTimeout: number | null = null;
    const handleResize = () => {
      if (resizeTimeout) {
        window.clearTimeout(resizeTimeout);
      }
      resizeTimeout = window.setTimeout(updateCanvasSize, 100);
    };
    
    window.addEventListener('resize', handleResize);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      if (resizeTimeout) {
        window.clearTimeout(resizeTimeout);
      }
    };
  }, [width, height]);

  // Force a re-render when target position changes
  useEffect(() => {
    if (targets && targets.length > 0) {
      const latestTarget = targets[targets.length - 1];
      const newPosition = latestTarget.position;
      
      // Check if position has changed
      if (!lastTargetPosition || 
          lastTargetPosition.x !== newPosition.x || 
          lastTargetPosition.y !== newPosition.y) {
        
        // Update state to trigger re-render
        setLastTargetPosition(newPosition);
        
        // Force an immediate render
        renderRadar();
      }
    }
  }, [targets, renderRadar, lastTargetPosition]);

  return (
    <div className="w-full h-full">
      <canvas
        ref={canvasRef}
        className="w-full h-full"
        style={{ 
          background: "black", 
          padding: "20px"
        }}
      />
    </div>
  );
} 