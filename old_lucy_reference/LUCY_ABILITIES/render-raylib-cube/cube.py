from pyray import *
import math

WIDTH = 900
HEIGHT = 650

init_window(WIDTH, HEIGHT, b"Lucy - Rotating raylib 3D Cube")
set_target_fps(60)

camera = Camera3D()
camera.position = Vector3(6.0, 4.0, 6.0)
camera.target = Vector3(0.0, 0.5, 0.0)
camera.up = Vector3(0.0, 1.0, 0.0)
camera.fovy = 45.0
camera.projection = CAMERA_PERSPECTIVE

angle = 0.0
camera_angle = 0.0

while not window_should_close():
    dt = get_frame_time()

    # Rotate the cube itself.
    angle += 55.0 * dt

    # Orbit the camera slowly so the rotation is unmistakably visible.
    camera_angle += 0.35 * dt
    camera.position = Vector3(
        math.cos(camera_angle) * 6.0,
        3.8 + math.sin(camera_angle * 0.7) * 0.7,
        math.sin(camera_angle) * 6.0
    )

    begin_drawing()
    clear_background(Color(20, 22, 28, 255))

    begin_mode_3d(camera)

    draw_grid(20, 1.0)

    # Use draw_cube_wires plus three rotating bars to make orientation obvious.
    draw_cube_v(Vector3(0, 1, 0), Vector3(2.0, 2.0, 2.0), Color(40, 120, 235, 255))
    draw_cube_wires_v(Vector3(0, 1, 0), Vector3(2.02, 2.02, 2.02), RAYWHITE)

    # Rotating orientation marker around the cube.
    a = math.radians(angle)
    marker = Vector3(math.cos(a) * 2.0, 1.0, math.sin(a) * 2.0)
    draw_sphere(marker, 0.22, RED)
    draw_line_3d(Vector3(0, 1, 0), marker, YELLOW)

    # Second marker makes the 3D motion easier to judge.
    marker2 = Vector3(
        math.cos(a + math.pi) * 1.6,
        1.0 + math.sin(a * 1.7) * 0.8,
        math.sin(a + math.pi) * 1.6
    )
    draw_sphere(marker2, 0.16, GREEN)
    draw_line_3d(Vector3(0, 1, 0), marker2, GREEN)

    end_mode_3d()

    draw_text(b"ROTATING 3D CUBE", 25, 22, 28, RAYWHITE)
    draw_text(b"Cube orientation markers + orbiting camera", 25, 58, 18, LIGHTGRAY)
    draw_text(b"ESC to close", 25, HEIGHT - 38, 18, GRAY)

    end_drawing()

close_window()
