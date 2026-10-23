"""Unit tests for the runtime camera color balance control."""

import unittest

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.camera import CameraManager
from backend.core import camera_manager
from backend.api.routes import router


app = FastAPI()
app.include_router(router)
client = TestClient(app)


class CameraColorBalanceTests(unittest.TestCase):
    def test_api_reads_and_updates_color_balance(self):
        original = camera_manager.color_balance
        try:
            response = client.post("/api/camera/color-balance", json={"value": 18})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["value"], 18)
            self.assertEqual(
                client.get("/api/camera/color-balance").json()["value"], 18
            )

            invalid = client.post("/api/camera/color-balance", json={"value": 51})
            self.assertEqual(invalid.status_code, 422)
        finally:
            camera_manager.set_color_balance(original)

    def test_neutral_balance_leaves_frame_unchanged(self):
        camera = CameraManager()
        frame = np.full((2, 2, 3), (80, 100, 120), dtype=np.uint8)

        adjusted = camera._apply_color_balance(frame)

        self.assertIs(adjusted, frame)
        np.testing.assert_array_equal(adjusted, frame)

    def test_warm_balance_increases_red_and_reduces_blue(self):
        camera = CameraManager()
        camera.set_color_balance(50)
        frame = np.full((1, 1, 3), (100, 100, 100), dtype=np.uint8)

        blue, green, red = camera._apply_color_balance(frame)[0, 0]

        self.assertLess(blue, green)
        self.assertLess(green, red)

    def test_cool_balance_increases_blue_and_reduces_red(self):
        camera = CameraManager()
        camera.set_color_balance(-50)
        frame = np.full((1, 1, 3), (100, 100, 100), dtype=np.uint8)

        blue, green, red = camera._apply_color_balance(frame)[0, 0]

        self.assertLess(red, green)
        self.assertLess(green, blue)

    def test_color_balance_is_clamped_to_slider_range(self):
        camera = CameraManager()

        self.assertEqual(camera.set_color_balance(500), 50)
        self.assertEqual(camera.set_color_balance(-500), -50)


if __name__ == "__main__":
    unittest.main()
