import torch
import numpy as np
from typing import Dict, List, Tuple

class AdvancedNoisePatterns:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "noise_params": ("NOISE_PARAMS",),
                "width": ("INT", {"default": 512, "min": 64, "max": 2048, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 2048, "step": 8}),
                "noise_type": (["simplex", "cellular", "fbm", "wave", "domain_warp"],),
                "analysis_type": ("ANALYSIS_TYPE",)
            }
        }

    RETURN_TYPES = ("LATENT", "TIMESTAMPS")
    FUNCTION = "generate_advanced_noise"
    CATEGORY = "audio/noise"

    def generate_simplex(self, shape, freq):
        coords = torch.stack(torch.meshgrid(
            torch.linspace(-np.pi, np.pi, shape[0]),
            torch.linspace(-np.pi, np.pi, shape[1])
        ))
        return torch.tanh(torch.sin(coords[0] * freq) * torch.cos(coords[1] * freq * 1.5)) * \
               torch.sigmoid(torch.cos(coords[0] * freq * 0.7) * torch.sin(coords[1] * freq * 2))

    def generate_cellular(self, shape, numPoints, chaos_factor=1.0):
        points = torch.rand(numPoints, 2) * torch.tensor(shape) * chaos_factor
        x = torch.arange(shape[0]).reshape(-1, 1).repeat(1, shape[1])
        y = torch.arange(shape[1]).reshape(1, -1).repeat(shape[0], 1)
        
        distances1 = torch.min(torch.sqrt(
            (x.reshape(-1, 1) - points[:, 0]) ** 2 +
            (y.reshape(-1, 1) - points[:, 1]) ** 2
        ), dim=1)[0].reshape(shape)
        
        distances2 = torch.min(torch.sqrt(
            (x.reshape(-1, 1) - points[:, 0] * 1.5) ** 2 +
            (y.reshape(-1, 1) - points[:, 1] * 0.8) ** 2
        ), dim=1)[0].reshape(shape)
        
        return torch.sin(distances1 * 0.2) * torch.cos(distances2 * 0.15)

    def generate_fbm(self, shape, octaves, persistence, lacunarity, chaos=1.0):
        noise = torch.zeros(shape)
        amplitude = 1.0
        frequency = 1.0
        
        for i in range(octaves):
            noise += amplitude * self.generate_simplex(shape, frequency * chaos)
            amplitude *= persistence * (1 + chaos * 0.2)
            frequency *= lacunarity * (1 + chaos * 0.1)
            
        return torch.tanh(noise)

    def generate_wave(self, shape, frequency, phases):
        x = torch.linspace(-np.pi, np.pi, shape[1])
        y = torch.linspace(-np.pi, np.pi, shape[0])
        xx, yy = torch.meshgrid(x, y)
        
        wave1 = torch.sin(xx * frequency + phases[0]) * torch.cos(yy * frequency * 1.3 + phases[1])
        wave2 = torch.cos(xx * frequency * 0.7 + phases[1]) * torch.sin(yy * frequency * 1.7 + phases[0])
        wave3 = torch.sin((xx + yy) * frequency * 0.5) * torch.cos((xx - yy) * frequency * 0.8)
        
        return (wave1 + wave2 + wave3) / 3

    def domain_warp(self, noise, warp_factor, timestamp):
        height, width = noise.shape
        grid_x, grid_y = torch.meshgrid(
            torch.linspace(-1, 1, width),
            torch.linspace(-1, 1, height)
        )
        
        warp = torch.stack([
            grid_x + warp_factor * torch.sin(6 * np.pi * timestamp + grid_y * 2) * torch.cos(grid_x * 3),
            grid_y + warp_factor * torch.cos(6 * np.pi * timestamp + grid_x * 2) * torch.sin(grid_y * 3)
        ])
        
        warped = torch.nn.functional.grid_sample(
            noise.unsqueeze(0).unsqueeze(0),
            warp.permute(1, 2, 0).unsqueeze(0),
            align_corners=False
        )[0, 0]
        
        return torch.tanh(warped * 2)

    def generate_advanced_noise(self, noise_params, width, height, noise_type, analysis_type):
        # Initialize default noise parameters if not provided
        default_noise_params = {
            "timestamps": [0.0, 0.5, 1.0],
            "simplex": {"intensity": 1.0},
            "cellular": {"intensity": 1.0},
            "fbm": {"intensity": 1.0, "persistence": 0.5},
            "wave": {"intensity": 1.0},
            "domain_warp": {"intensity": 1.0}
        }
        
        # Merge provided parameters with defaults
        if not noise_params:
            noise_params = default_noise_params
        else:
            for key in default_noise_params:
                if key not in noise_params:
                    noise_params[key] = default_noise_params[key]
        
        timestamps = noise_params["timestamps"]
        if len(timestamps) == 0:
            return ({"samples": torch.zeros((1, 4, height//8, width//8))}, [0.0])
        
        batch_size = len(timestamps)
        latent_height, latent_width = height//8, width//8
        noise_batch = torch.zeros((batch_size, 4, latent_height, latent_width))
        
        base_params = noise_params[noise_type]
        intensity = base_params.get("intensity", 1.0)
        persistence = base_params.get("persistence", 0.5)

        for i, timestamp in enumerate(timestamps):
            time_scale = (timestamp / timestamps[-1]) ** 0.3
            energy_factor = intensity * (1 + np.exp(time_scale * 2) - 1)
            chaos = 0.5 + abs(np.sin(timestamp * 10)) * 2
            
            if noise_type == "simplex":
                freq = 1 + energy_factor * 30
                base_noise = self.generate_simplex((latent_height, latent_width), freq)
                
            elif noise_type == "cellular":
                points = int(3 + energy_factor * 150)
                base_noise = self.generate_cellular((latent_height, latent_width), points, chaos)
                
            elif noise_type == "fbm":
                octaves = int(2 + energy_factor * 6)
                persistence = 0.2 + energy_factor * 0.8
                lacunarity = 1.2 + energy_factor * 4
                base_noise = self.generate_fbm((latent_height, latent_width), octaves, persistence, lacunarity, chaos)
                
            elif noise_type == "wave":
                freq = 0.3 + energy_factor * 12
                phase_x = timestamp * 8 * np.pi * chaos
                phase_y = timestamp * 6 * np.pi * (2 - chaos)
                base_noise = self.generate_wave((latent_height, latent_width), freq, [phase_x, phase_y])
                
            elif noise_type == "domain_warp":
                base_noise = self.generate_simplex((latent_height, latent_width), 2 * chaos)
                warp_factor = 0.1 + energy_factor * 1.2
                base_noise = self.domain_warp(base_noise, warp_factor, timestamp)

            base_noise = (base_noise - base_noise.min()) / (base_noise.max() - base_noise.min())
            
            for c in range(4):
                channel_phase = c * np.pi / 2 * chaos
                channel_noise = torch.sin(base_noise * (8 + channel_phase)) * energy_factor
                noise_batch[i, c] = torch.tanh(channel_noise * 2)

        return ({"samples": noise_batch}, timestamps)

NODE_CLASS_MAPPINGS = {
    "AdvancedNoisePatterns": AdvancedNoisePatterns
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AdvancedNoisePatterns": "Advanced Audio Noise Patterns"
}