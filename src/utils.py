from math import sqrt

def get_arch_centre(detection, x, y):
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

    d = directions[detection[0]]
    
    return (x+d[0]*detection[2], y+d[1]*detection[2])
