"""zGPU Graphics Pipeline: Triangle Rasterizer, Interpolation, & Fragment Shader."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Vertex:
    x: float
    y: float
    z: float
    r: float
    g: float
    b: float


class Framebuffer:
    def __init__(self, width: int = 64, height: int = 64):
        self.width = width
        self.height = height
        # Color buffer (RGB tuples) and Depth buffer (Z-buffer)
        self.color = [[(0, 0, 0) for _ in range(width)] for _ in range(height)]
        self.depth = [[1.0 for _ in range(width)] for _ in range(height)]

    def clear(self, color=(0, 0, 0)):
        for y in range(self.height):
            for x in range(self.width):
                self.color[y][x] = color
                self.depth[y][x] = 1.0


class Rasterizer:
    """Fixed-function and programmable fragment rasterizer simulating GPU ROPs."""

    @staticmethod
    def edge_function(a: Vertex, b: Vertex, c: tuple[float, float]) -> float:
        return (c[0] - a.x) * (b.y - a.y) - (c[1] - a.y) * (b.x - a.x)

    def draw_triangle(
        self,
        fb: Framebuffer,
        v0: Vertex,
        v1: Vertex,
        v2: Vertex,
        fragment_shader: (
            Callable[[float, float, float, tuple[float, float, float]], tuple[int, int, int]] | None
        ) = None,
    ):
        # Bounding box
        min_x = max(0, math.floor(min(v0.x, v1.x, v2.x)))
        max_x = min(fb.width - 1, math.ceil(max(v0.x, v1.x, v2.x)))
        min_y = max(0, math.floor(min(v0.y, v1.y, v2.y)))
        max_y = min(fb.height - 1, math.ceil(max(v0.y, v1.y, v2.y)))

        area = self.edge_function(v0, v1, (v2.x, v2.y))
        if abs(area) < 1e-6:
            return

        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                p = (x + 0.5, y + 0.5)
                w0 = self.edge_function(v1, v2, p)
                w1 = self.edge_function(v2, v0, p)
                w2 = self.edge_function(v0, v1, p)

                # If inside triangle (barycentric coordinates)
                if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                    b0 = w0 / area
                    b1 = w1 / area
                    b2 = w2 / area

                    # Interpolate Z depth
                    z = b0 * v0.z + b1 * v1.z + b2 * v2.z

                    # Depth test (Early-Z / ROP)
                    if z < fb.depth[y][x]:
                        fb.depth[y][x] = z

                        # Interpolate vertex colors
                        r = b0 * v0.r + b1 * v1.r + b2 * v2.r
                        g = b0 * v0.g + b1 * v1.g + b2 * v2.g
                        b = b0 * v0.b + b1 * v1.b + b2 * v2.b

                        if fragment_shader:
                            final_color = fragment_shader(x / fb.width, y / fb.height, z, (r, g, b))
                        else:
                            final_color = (int(r * 255), int(g * 255), int(b * 255))

                        fb.color[y][x] = final_color
