"""
Human Behavior Simulation
Adds randomness and human-like patterns to avoid bot detection
"""

import random
import time

def random_delay(min_seconds=1, max_seconds=3):
    """Random delay between actions"""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

def random_mouse_movement(page):
    """Simulate random mouse movements"""
    try:
        # Get viewport dimensions
        viewport = page.viewport_size
        width = viewport['width']
        height = viewport['height']

        # Move mouse to random positions
        for _ in range(random.randint(2, 5)):
            x = random.randint(100, width - 100)
            y = random.randint(100, height - 100)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.1, 0.3))
    except:
        pass

def random_scroll(page):
    """Simulate human-like scrolling"""
    try:
        # Scroll down in random increments
        scroll_amount = 0
        max_scroll = random.randint(500, 1500)

        while scroll_amount < max_scroll:
            increment = random.randint(50, 200)
            page.evaluate(f"window.scrollBy(0, {increment})")
            scroll_amount += increment
            time.sleep(random.uniform(0.1, 0.4))

        # Sometimes scroll back up a bit
        if random.random() > 0.5:
            page.evaluate(f"window.scrollBy(0, -{random.randint(100, 300)})")
            time.sleep(random.uniform(0.2, 0.5))
    except:
        pass

def simulate_reading(page, min_seconds=2, max_seconds=5):
    """Simulate reading the page"""
    read_time = random.uniform(min_seconds, max_seconds)

    # During reading, occasionally move mouse
    start = time.time()
    while time.time() - start < read_time:
        if random.random() > 0.7:
            random_mouse_movement(page)
        time.sleep(random.uniform(0.5, 1.5))
