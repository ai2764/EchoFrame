from app.config import Settings
from app.services.comfy import ComfyClient


def test_wan_workflow_uses_official_wan_image_to_video_node(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", wan_profile="wan22_14b_i2v")
    workflow = ComfyClient(settings)._wan_workflow(
        image_name="avatar.png",
        prompt="subtle talking head movement",
        video_prefix="test_wan",
        length=17,
        seed=123,
        width=320,
        height=320,
    )
    prompt = workflow["prompt"]

    assert prompt["13"]["class_type"] == "WanImageToVideo"
    assert prompt["18"]["class_type"] == "LoraLoaderModelOnly"
    assert prompt["18"]["inputs"]["model"] == ["1", 0]
    assert prompt["18"]["inputs"]["lora_name"] == settings.wan_high_lora
    assert prompt["19"]["class_type"] == "LoraLoaderModelOnly"
    assert prompt["19"]["inputs"]["model"] == ["2", 0]
    assert prompt["19"]["inputs"]["lora_name"] == settings.wan_low_lora
    assert prompt["3"]["inputs"]["model"] == ["18", 0]
    assert prompt["4"]["inputs"]["model"] == ["19", 0]
    assert prompt["13"]["inputs"]["positive"] == ["11", 0]
    assert prompt["13"]["inputs"]["negative"] == ["12", 0]
    assert prompt["14"]["inputs"]["positive"] == ["13", 0]
    assert prompt["14"]["inputs"]["negative"] == ["13", 1]
    assert prompt["14"]["inputs"]["latent_image"] == ["13", 2]
    assert prompt["14"]["inputs"]["steps"] == 4
    assert prompt["14"]["inputs"]["end_at_step"] == 2
    assert prompt["14"]["inputs"]["sampler_name"] == "euler"
    assert prompt["15"]["inputs"]["positive"] == ["13", 0]
    assert prompt["15"]["inputs"]["negative"] == ["13", 1]
    assert prompt["15"]["inputs"]["latent_image"] == ["14", 0]
    assert prompt["15"]["inputs"]["steps"] == 4
    assert prompt["15"]["inputs"]["start_at_step"] == 2
    assert prompt["15"]["inputs"]["end_at_step"] == 4


def test_wan_5b_workflow_uses_official_ti2v_nodes(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", wan_profile="wan22_5b_ti2v")
    workflow = ComfyClient(settings)._wan_workflow(
        image_name="avatar.png",
        prompt="subtle talking head movement",
        video_prefix="test_wan_5b",
        length=17,
        seed=123,
        width=320,
        height=320,
    )
    prompt = workflow["prompt"]

    assert prompt["1"]["class_type"] == "UNETLoader"
    assert prompt["1"]["inputs"]["unet_name"] == settings.wan_5b_model
    assert prompt["2"]["class_type"] == "ModelSamplingSD3"
    assert prompt["2"]["inputs"]["model"] == ["1", 0]
    assert prompt["3"]["class_type"] == "CLIPLoader"
    assert prompt["4"]["class_type"] == "VAELoader"
    assert prompt["4"]["inputs"]["vae_name"] == settings.wan_5b_vae_model
    assert prompt["8"]["class_type"] == "Wan22ImageToVideoLatent"
    assert prompt["8"]["inputs"]["start_image"] == ["5", 0]
    assert prompt["8"]["inputs"]["width"] == 320
    assert prompt["8"]["inputs"]["height"] == 320
    assert prompt["9"]["class_type"] == "KSampler"
    assert prompt["9"]["inputs"]["sampler_name"] == settings.wan_5b_sampler
    assert prompt["9"]["inputs"]["steps"] == settings.wan_5b_steps
    assert prompt["11"]["class_type"] == "CreateVideo"
    assert prompt["12"]["class_type"] == "SaveVideo"
    assert "18" not in prompt
