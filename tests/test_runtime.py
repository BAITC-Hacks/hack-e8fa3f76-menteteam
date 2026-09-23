import pytest


def test_t4_uses_cuda_float16_and_missing_gpu_is_explicit():
    from adapters.runtime import choose_runtime
    assert choose_runtime("cuda", True, (7, 5)) == ("cuda", "float16")
    assert choose_runtime("cpu", True, (7, 5)) == ("cpu", "float32")
    assert choose_runtime("auto", False) == ("cpu", "float32")
    with pytest.raises(RuntimeError, match="CUDA"):
        choose_runtime("cuda", False)


def test_switching_phase_releases_previous_models():
    from adapters.runtime import ModelLifecycle
    resources = {"speech": True, "gemma": True}
    lifecycle = ModelLifecycle()
    lifecycle.register("speech", lambda: resources.update(speech=False))
    lifecycle.register("gemma", lambda: resources.update(gemma=False))
    lifecycle.activate("speech")
    assert resources == {"speech": True, "gemma": False}
    resources["gemma"] = True
    lifecycle.activate("gemma")
    assert resources == {"speech": False, "gemma": True}
