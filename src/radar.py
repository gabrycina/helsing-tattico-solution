import pygame
import threading
import time
import random
import math


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
        self.scanner_angle = 0  # Angle for the rotating scanner
        # Turquoise color scheme
        self.radar_color = (0, 255, 238)  # Bright turquoise
        self.grid_color = (0, 180, 170)  # Darker turquoise
        self.scanner_color = (0, 255, 238)  # Scanner color
        # Control flag
        self.running = threading.Event()

    def draw_background(self):
        """Draw the black background."""
        self.screen.fill((0, 15, 15))  # Very dark turquoise for background

    def create_gradient_surface(self, radius):
        """Create a radial gradient surface for the scanner effect."""
        gradient = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        center = radius, radius

        for i in range(radius, 0, -1):
            alpha = int((1 - (i / radius)) * 50)  # Gradient transparency
            pygame.draw.circle(gradient, (*self.scanner_color, alpha), center, i)

        return gradient

    def draw_scanner(self, center, radius):
        """Draw the rotating scanner line with gradient."""
        # Calculate scanner line end point
        end_x = center[0] + radius * math.cos(math.radians(self.scanner_angle))
        end_y = center[1] - radius * math.sin(math.radians(self.scanner_angle))

        # Create a surface for the scanner gradient
        scanner_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        # Draw the scanner line
        pygame.draw.line(
            scanner_surface, (*self.scanner_color, 255), center, (end_x, end_y), 2
        )

        # Create a pie-shaped gradient sector
        angle_rad = math.radians(self.scanner_angle)
        points = [center]
        num_points = 20
        for i in range(num_points):
            angle = angle_rad - math.pi / 8 + (i * math.pi / (4 * num_points))
            x = center[0] + radius * math.cos(angle)
            y = center[1] - radius * math.sin(angle)
            points.append((x, y))
        points.append(center)

        # Draw the gradient sector
        if len(points) > 2:
            pygame.draw.polygon(scanner_surface, (*self.scanner_color, 32), points)

        self.screen.blit(scanner_surface, (0, 0))

        # Update scanner angle
        self.scanner_angle = (
            self.scanner_angle + 2
        ) % 360  # Rotate 2 degrees per frame

    def draw_radar_circle(self):
        """Draw the green radar circle with a lighter green and more transparency."""
        # Create a semi-transparent surface for the radar circle
        radar_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        center = (self.width // 2, self.height // 2)
        radius = min(self.width, self.height) // 2 - 10

        # Draw main radar circle
        pygame.draw.circle(
            radar_surface, (*self.radar_color, 32), center, radius
        )  # Main circle
        pygame.draw.circle(
            radar_surface, (*self.radar_color, 64), center, radius, 2
        )  # Outer ring

        self.screen.blit(radar_surface, (0, 0))

        # Draw the scanner
        self.draw_scanner(center, radius)

    def draw_axes(self):
        """Draw the x and y axes on the radar."""
        center = (self.width // 2, self.height // 2)
        radius = min(self.width, self.height) // 2 - 10

        # Draw a light green grid with concentric circles
        for r in range(20, radius, 60):  # Increase spacing between circles
            pygame.draw.circle(
                self.screen, self.grid_color, center, r, 1
            )  # Light green circles

        # Draw x-axis
        pygame.draw.line(
            self.screen,
            self.radar_color,
            (center[0] - radius, center[1]),
            (center[0] + radius, center[1]),
            2,
        )

        # Draw y-axis
        pygame.draw.line(
            self.screen,
            self.radar_color,
            (center[0], center[1] - radius),
            (center[0], center[1] + radius),
            2,
        )

        # Draw labels for the axes
        font = pygame.font.Font(None, 24)
        for x in range(-100, 101, 20):
            if x == 0:  # Skip the origin label for x-axis
                continue
            x_pos = center[0] + x * (radius // 100)
            if abs(x_pos - center[0]) <= radius:  # Ensure labels are within the circle
                label = font.render(str(x), True, self.radar_color)
                self.screen.blit(label, (x_pos - 10, center[1] + 5))

        for y in range(-100, 101, 20):
            if y == 0:  # Skip the origin label for y-axis
                continue
            y_pos = center[1] - y * (radius // 100)
            if abs(y_pos - center[1]) <= radius:  # Ensure labels are within the circle
                label = font.render(str(y), True, self.radar_color)
                self.screen.blit(label, (center[0] + 5, y_pos - 10))

    def draw_unit(self, unit_id, x, y, color=(0, 255, 238)):
        """Draw or update a unit on the radar."""
        # Update the unit's position in the dictionary
        self.units[unit_id] = (x, y, color)

        # Draw all units
        for uid, (ux, uy, color) in self.units.items():
            # Convert coordinates to screen space
            center = (self.width // 2, self.height // 2)
            radius = min(self.width, self.height) // 2 - 10
            screen_x = center[0] + int(ux * (radius // 100))
            screen_y = center[1] - int(uy * (radius // 100))

            # Draw the unit as a red circle
            pygame.draw.circle(self.screen, color, (screen_x, screen_y), 10)

    def draw_target(self, x, y):
        """Draw a target on the radar as a triangle that fades away over 2 seconds without blocking the main thread."""
        # Save the target coordinates and set initial opacity
        self.target_coords = (x, y)
        self.target_opacity = 255
        
        if self.target_coords is not None:
            center = (self.width // 2, self.height // 2)
            radius = min(self.width, self.height) // 2 - 10
            screen_x = center[0] + int(x * (radius // 100))
            screen_y = center[1] - int(y * (radius // 100))

            # Create a surface to handle opacity
            target_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

            # Define the points of the triangle
            triangle_points = [
                (screen_x, screen_y - 15),  # Top point
                (screen_x - 10, screen_y + 10),  # Bottom-left point
                (screen_x + 10, screen_y + 10),  # Bottom-right point
            ]

            # Draw the triangle
            pygame.draw.polygon(
                target_surface, (255, 0, 0, self.target_opacity), triangle_points
            )
            self.screen.blit(target_surface, (0, 0))

    def success(self):
        """Display success message and stop the radar."""
        self.running.clear()
        # Draw everything one last time
        self.draw_background()
        self.draw_radar_circle()
        self.draw_axes()
        
        # Create a large font for the success message
        font = pygame.font.Font(None, 120)  # Large font size
        text = font.render("SUCCESS", True, (255, 255, 255))  # White text
        
        # Get the text rectangle and center it
        text_rect = text.get_rect()
        text_rect.center = (self.width // 2, self.height // 2)
        
        # Draw a semi-transparent black background behind the text
        bg_surface = pygame.Surface((text_rect.width + 40, text_rect.height + 40))
        bg_surface.fill((0, 0, 0))
        bg_surface.set_alpha(128)
        bg_rect = bg_surface.get_rect()
        bg_rect.center = (self.width // 2, self.height // 2)
        self.screen.blit(bg_surface, bg_rect)
        
        # Draw the text
        self.screen.blit(text, text_rect)
        pygame.display.flip()
        
        # Keep the text visible for a moment
        
        # Stop the radar

    def run(self):
        """Run the radar display loop."""
        self.running.set()
        while self.running.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running.clear()
                    break

            self.draw_background()
            self.draw_radar_circle()
            self.draw_axes()

            # Draw all units
            for unit_id, values in self.units.items():
                self.draw_unit(unit_id, values[0], values[1], values[2])

            # Draw the target if coordinates are available
            if self.target_coords is not None:
                x, y = self.target_coords
                center = (self.width // 2, self.height // 2)
                radius = min(self.width, self.height) // 2 - 10
                screen_x = center[0] + int(x * (radius // 100))
                screen_y = center[1] - int(y * (radius // 100))

                # Create a surface to handle opacity
                target_surface = pygame.Surface(
                    (self.width, self.height), pygame.SRCALPHA
                )

                # Define the points of the triangle
                triangle_points = [
                    (screen_x, screen_y - 15),  # Top point
                    (screen_x - 10, screen_y + 10),  # Bottom-left point
                    (screen_x + 10, screen_y + 10),  # Bottom-right point
                ]

                # Draw the triangle
                pygame.draw.polygon(
                    target_surface, (255, 0, 0, self.target_opacity), triangle_points
                )
                self.screen.blit(target_surface, (0, 0))

            pygame.display.flip()
            self.clock.tick(60)

        time.sleep(8)
        pygame.quit()


if __name__ == "__main__":
    radar = Radar()

    def update_units():
        """Simulate unit updates."""
        unit_id = 1
        x = 50
        y = 50
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
