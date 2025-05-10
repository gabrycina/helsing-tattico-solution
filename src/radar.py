import pygame
import threading
import time
import random

class Radar:
    def __init__(self, width=800, height=800):
        """Initialize the Radar class with a pygame window."""
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Radar Coordinate System")
        self.clock = pygame.time.Clock()
        self.units = {}  # Dictionary to store unit positions by ID
        self.target_coords = None  # To store the target coordinates
        self.target_opacity = 0  # To store the target's opacity level

    def draw_axes(self):
        """Draw the x and y axes on the screen."""
        # Set the background color to black
        self.screen.fill((0, 0, 0))  # Black

        # Draw a military green circle for the coordinate system
        center = (self.width // 2, self.height // 2)
        radius = min(self.width, self.height) // 2 - 10
        pygame.draw.circle(self.screen, (85, 107, 47), center, radius)  # Military green

        # Draw a light green grid with concentric circles
        for r in range(20, radius, 20):  # Increment radius by 20 for each circle
            pygame.draw.circle(self.screen, (144, 238, 144), center, r, 1)  # Light green circles

        # Draw x-axis
        pygame.draw.line(self.screen, (0, 0, 0), (center[0] - radius, center[1]), (center[0] + radius, center[1]), 2)

        # Draw y-axis
        pygame.draw.line(self.screen, (0, 0, 0), (center[0], center[1] - radius), (center[0], center[1] + radius), 2)

        # Draw labels for the axes
        font = pygame.font.Font(None, 24)
        for x in range(-100, 101, 20):
            if x == 0:  # Skip the origin label for x-axis
                continue
            x_pos = center[0] + x * (radius // 100)
            if abs(x_pos - center[0]) <= radius:  # Ensure labels are within the circle
                label = font.render(str(x), True, (0, 0, 0))
                self.screen.blit(label, (x_pos - 10, center[1] + 5))

        for y in range(-100, 101, 20):
            if y == 0:  # Skip the origin label for y-axis
                continue
            y_pos = center[1] - y * (radius // 100)
            if abs(y_pos - center[1]) <= radius:  # Ensure labels are within the circle
                label = font.render(str(y), True, (0, 0, 0))
                self.screen.blit(label, (center[0] + 5, y_pos - 10))

    def draw_unit(self, unit_id, x, y):
        """Draw or update a unit on the radar."""
        # Update the unit's position in the dictionary
        self.units[unit_id] = (x, y)

        # Draw all units
        for uid, (ux, uy) in self.units.items():
            # Convert coordinates to screen space
            center = (self.width // 2, self.height // 2)
            radius = min(self.width, self.height) // 2 - 10
            screen_x = center[0] + int(ux * (radius // 100))
            screen_y = center[1] - int(uy * (radius // 100))

            # Draw the unit as a red circle
            pygame.draw.circle(self.screen, (0, 0, 255), (screen_x, screen_y), 5)

    def draw_target(self, x, y):
        """Draw a target on the radar that fades away over 2 seconds without blocking the main thread."""
        # Save the target coordinates and set initial opacity
        self.target_coords = (x, y)
        self.target_opacity = 255

        def fade_target():
            for step in range(20):  # 20 steps over 2 seconds
                time.sleep(0.1)  # Wait 0.1 seconds per step
                self.target_opacity = max(0, self.target_opacity - 255 // 20)  # Decrease opacity

            # Clear the target coordinates and opacity
            self.target_coords = None
            self.target_opacity = 0

        # Start a thread to handle the fading target
        threading.Thread(target=fade_target, daemon=True).start()

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            self.draw_axes()

            # Draw all units
            for unit_id, (x, y) in self.units.items():
                self.draw_unit(unit_id, x, y)

            # Draw the target if coordinates are available
            if self.target_coords is not None:
                x, y = self.target_coords
                center = (self.width // 2, self.height // 2)
                radius = min(self.width, self.height) // 2 - 10
                screen_x = center[0] + int(x * (radius // 100))
                screen_y = center[1] - int(y * (radius // 100))

                # Create a surface to handle opacity
                target_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                pygame.draw.circle(target_surface, (255, 0, 0, self.target_opacity), (screen_x, screen_y), 5)
                self.screen.blit(target_surface, (0, 0))

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


if __name__ == "__main__":
    radar = Radar()

    def update_units():
        """Simulate unit updates."""
        unit_id = 1
        x = 50
        y= 50
        while True:
            # Simulate random movement
            radar.draw_unit(unit_id, x, y)
            x += 10
            y -= 10

            if random.randint(0, 10) < 2:  # Randomly trigger a target
                radar.draw_target(40, 25)

            time.sleep(1)
    # Start a thread to update units
    unit_thread = threading.Thread(target=update_units)
    unit_thread.daemon = True  # Daemonize thread
    unit_thread.start()

    radar.run()

