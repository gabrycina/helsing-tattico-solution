# LDTH 2025 - Helsing Coordination Challenge

> Distributed mobile systems design for the London Defence Tech Hackathon, May
> 2025. Designed and run by Helsing.

## Challenge Prompt

When dealing of swarms of drones, gliders and other autonomous units, one
of the most important aspects of tasking is context sharing. Each unit only
has limited local information about the world, which may not be sufficient
for the task at hand. Sometimes a strike unit needs to rely on input from a
reconnaissance unit to navigate effectively, as the former is generally equipped
with better sensors.

The goal of this challenge is to deal with just such a scenario. You're in
charge of five units total, 4 sensors and 1 strike unit, and the goal is to
navigate the strike unit to a moving target. The strike unit is blind: it must
rely on information from other units to effectively navigate. This is where
communication and coordination becomes important.

We will provide contestants with access to an API that can be used to start and
manage simulations of this scenario, giving contestants control over each unit
individually.

**Important**: control logic of each unit must only take into account local
information provided by the API, and any state sharing must be done exclusively
through the provided API. Shared memory, IPC or any other side-channels used
directly or indirectly to guide the units will be grounds for disqualifying
a solution.

### Getting started

We provide [a protobuf schema] that can be used to generate a client to interact
with our web service.

The challenge server is running at 172 dot 237 dot 124 dot 96, port 21234.

#### Authentication

For the challenge, we've enabled a "Bring Your Own Token" authentication model.
This means you can select your own token and send it with requests using the
`authorization` header, with the usual `bearer <token>` value format. Just
ensure you reuse the same value for all requests you make.

#### The simulation

The simulation runs in a 2D environment, bounded by a square of 100 by 100
units. All entities are spawned within this region, and the target will never
leave it, but your units might if they drift off. There are some simplified
physics features, so take inertia into account when planning your navigation.
Units can accelerate in any direction.

We have implemented the following entities:

##### The home base

This does nothing, but simply acts as an anchor point around which all units
are spawned. The target will generally avoid this location, but may get close.

##### The sensor units

These are your eyes in the field. They can move around and detect obstacles and
the target. They can share messages among themselves, and the strike unit. They
are indestructible in this simulation, but cannot overcome obstacles.

##### The obstacles

These are static objects that merely exist to make navigation more complicated.
They can be detected by sensors and easily circumvented. No mobile entities
(including the target) are able to pass through them.

##### The target

This is a mobile entity that will move around constantly. Your goal is to collide
with it using the strike unit.

##### The strike unit

This is your weapon at hand. Once launched, you must direct it to the target
to complete the simulation. It possesses no sensors of its own, so you must use
information from friendly sensor units to navigate. This can be done via the
message passing interface.

If you fail to strike the target within a time limit, the simulation
automatically times out. There is no penalty for failure - you can just start a
fresh simulation.

#### API usage guide

##### Starting a simulation

Starting a simulation can be done with the `Start` endpoint. It returns a
set of initial parameters for the simulation, including the initial position
of your sensor units, and the base position. The strike unit will launch
from close to the base once you trigger that action.

##### Controlling units

To take control of individual units (including the strike unit, once launched),
use the `UnitControl` endpoint. It expects a stream of commands as input, and
returns a stream of statuses, which are sent each time the simulation updates.

To specify which simulation and unit you wish to take control of, use two special
request headers:

`x-simulation-id`: the simulation-id returned by the call to `Start`.
`x-unit-id`: the unit-id of the unit you wish to control. This is also returned
from the `Start` call.

Sensor updates include their current position, a set of detections and messages
received since the last update.

Detections are always associated with a cardinal direction, a class and
a distance. The class stands for Obstacle or Target. The distance is only
approximate. Note that cardinal directions are only accurate down to 45 degrees,
and the error gets larger the more distant the detection. You may use multiple
sensors to pinpoint a detection more accurately, by passing messages between
them (assuming they are in range for detection). Since the strike unit is blind,
these detections are essential for striking the target accurately. They can also
be used to help with navigation.

Messages can be any arbitrary payload. You can share any information between units
you wish, as long as this information sharing takes place over the API. No bird's
eye view solutions allowed! Each unit should be controlled independently, using only
local information and message passing.

As for commands, units can move around by applying an impulse command (which takes
a 2D vector representing an acceleration delta), and can send message commands to
communicate. Messages sent will be received at the next simulation tick by other
units. If you leave the `dst` field empty, this implies a broadcast message.

##### Launching the strike unit

Once you're ready to strike, launch the strike unit by calling the
`LaunchStrikeUnit` endpoint. This takes a simulation-id as argument, and
produces a payload with the unit-id and its position. You can then control it
as normal using the `UnitControl` endpoint - the only difference is its status
updates will never contain any detections.

##### Ending a simulation

Once you manage to hit the target by colliding the strike unit with it, the
simulation will end automatically, terminating all active streams. You can
confirm a successful outcome by calling the `GetSimulationStatus` endpoint
afterwards.

If you fail to hit the target within a certain timeframe, it will automatically
time out. This can be verified using the same endpoint.

#### One last note

Don't forget to have fun! We'd love to see what sort of creative ideas you come up.


[a protobuf schema]: ./simulation.proto
