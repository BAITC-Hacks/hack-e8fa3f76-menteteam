"""Explicit compute selection and sequential model residency for a 16 GB T4."""
import gc
import os
import sys
from threading import RLock

INFERENCE_LOCK = RLock()


def choose_runtime(requested: str, cuda_available: bool, capability=(0, 0)) -> tuple[str, str]:
    if requested not in {"auto", "cuda", "cpu"}:
        raise ValueError("AI_DEVICE должен быть cuda, cpu или auto.")
    if requested == "cuda" and not cuda_available:
        raise RuntimeError("CUDA недоступна. Проверьте драйвер NVIDIA, доступ к GPU и CUDA-сборку PyTorch. Для CPU задайте AI_DEVICE=cpu явно.")
    device = "cuda" if requested != "cpu" and cuda_available else "cpu"
    dtype = "float32" if device == "cpu" else ("bfloat16" if capability[0] >= 8 else "float16")
    return device, dtype


def runtime():
    import torch
    available = torch.cuda.is_available()
    capability = torch.cuda.get_device_capability() if available else (0, 0)
    return choose_runtime(os.getenv("AI_DEVICE", "cuda"), available, capability)


class ModelLifecycle:
    def __init__(self):
        self.phase = None
        self.releasers = {}

    def register(self, phase, release):
        self.releasers[phase] = release

    def activate(self, phase):
        if self.phase == phase:
            return
        for name, release in self.releasers.items():
            if name != phase:
                release()
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
        self.phase = phase


lifecycle = ModelLifecycle()
