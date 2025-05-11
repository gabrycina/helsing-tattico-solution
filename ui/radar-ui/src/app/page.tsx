"use client";

import { RadarDisplay } from "@/components/radar-display";
import { useRadarSocket } from "@/lib/websocket";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export default function Home() {
  const { isConnected, radarData } = useRadarSocket("ws://localhost:8765");

  return (
    <div className="fixed inset-0 bg-black">
      {/* Status overlay - smaller and more transparent */}
      <div className="absolute top-1 left-1 z-10 opacity-70 hover:opacity-100 transition-opacity flex items-center gap-1">
        <Badge 
          variant={isConnected ? "secondary" : "destructive"} 
          className={`uppercase font-mono text-[9px] tracking-wide px-1 py-0 ${isConnected ? 'bg-emerald-900/60 hover:bg-emerald-800/80 text-emerald-300' : ''}`}
        >
          {isConnected ? 'CONN' : 'OFF'}
        </Badge>
        
        <Dialog>
          <DialogTrigger asChild>
            <Button 
              variant="outline" 
              className="h-4 text-[9px] font-mono tracking-wide border-emerald-900/20 text-emerald-500/80 hover:bg-emerald-900/10 bg-transparent px-1"
            >
              ?
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-black/90 border-emerald-900/30 text-emerald-100 font-mono max-w-xs">
            <DialogHeader>
              <DialogTitle className="text-emerald-400 tracking-wider text-xs">RADAR GUIDE</DialogTitle>
            </DialogHeader>
            <div className="py-1 text-[10px]">
              <ul className="space-y-1 text-emerald-100/80">
                <li className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-blue-400"></span> Sensor units</li>
                <li className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-pink-400"></span> Strike unit</li>
                <li className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-green-400"></span> Base position</li>
              </ul>
            </div>
          </DialogContent>
        </Dialog>
      </div>
      
      {/* Tactical title - smaller */}
      <div className="absolute top-1 left-1/2 transform -translate-x-1/2 z-10">
        <p className="text-center text-[9px] text-emerald-400/70 font-mono tracking-wide">
          TACTICAL RADAR
        </p>
      </div>
      
      {/* Classification label - smaller */}
      <div className="absolute bottom-0.5 left-1/2 transform -translate-x-1/2 z-10">
        <p className="text-center text-[8px] text-emerald-900/80 font-mono tracking-wide">
          CLASSIFICATION: TOP SECRET
        </p>
      </div>

      {/* Fullscreen radar */}
      <div className="w-full h-full">
        <RadarDisplay
          units={radarData.units}
          targets={radarData.targets}
          basePosition={radarData.basePosition}
          successMessage={radarData.successMessage}
        />
      </div>
    </div>
  );
}
