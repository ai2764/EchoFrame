import asyncio

from app.config import Settings
from app.modules.video import VideoGenerationModule
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


def test_ltx_ia2v_workflow_uses_image_audio_inputs(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v", ltx_model_format="checkpoint")
    workflow = ComfyClient(settings)._ltx_ia2v_workflow(
        image_name="avatar.png",
        audio_name="voice.wav",
        prompt="natural talking avatar",
        video_prefix="test_ltx",
        duration=3.2,
        seed=123,
        width=768,
        height=768,
        fps=24,
    )
    prompt = workflow["prompt"]

    assert prompt["900"]["class_type"] == "LoadImage"
    assert prompt["900"]["inputs"]["image"] == "avatar.png"
    assert prompt["901"]["class_type"] == "LoadAudio"
    assert prompt["901"]["inputs"]["audio"] == "voice.wav"
    assert prompt["319"]["inputs"]["value"] == "natural talking avatar"
    assert prompt["330"]["inputs"]["value"] == 768
    assert prompt["324"]["inputs"]["value"] == 768
    assert prompt["302"]["inputs"]["width"] == 384
    assert prompt["302"]["inputs"]["height"] == 384
    assert prompt["302"]["inputs"]["length"] == 81
    assert prompt["307"]["inputs"]["frame_rate"] == 24
    assert prompt["312"]["inputs"]["fps"] == 24
    assert prompt["297"]["inputs"]["scale_method"] == "lanczos"
    assert "resize_type.upscale_method" not in prompt["297"]["inputs"]
    assert prompt["328"]["inputs"]["audio"] == ["901", 0]
    assert "332" not in prompt
    assert "ComfyMathExpression" not in {node["class_type"] for node in prompt.values()}
    assert prompt["328"]["class_type"] == "LTXVAudioVAEEncode"
    assert prompt["312"]["class_type"] == "CreateVideo"
    assert prompt["999"]["class_type"] == "SaveVideo"
    assert prompt["999"]["inputs"]["filename_prefix"] == "test_ltx"


def test_ltx_native_audio_workflow_uses_empty_audio_latent(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_native_audio", ltx_model_format="checkpoint")
    workflow = ComfyClient(settings)._ltx_ia2v_workflow(
        image_name="avatar.png",
        audio_name="",
        prompt="the person says hello with generated speech audio",
        video_prefix="test_ltx_native",
        duration=3.2,
        seed=123,
        width=320,
        height=320,
        fps=24,
        native_audio=True,
    )
    prompt = workflow["prompt"]

    assert prompt["900"]["class_type"] == "LoadImage"
    assert "901" not in prompt
    assert "327" not in prompt
    assert "333" not in prompt
    assert prompt["326"]["inputs"]["audio_latent"] == ["328", 0]
    assert prompt["328"]["class_type"] == "LTXVEmptyLatentAudio"
    assert prompt["328"]["inputs"]["frames_number"] == 81
    assert prompt["328"]["inputs"]["frame_rate"] == 24
    assert prompt["328"]["inputs"]["audio_vae"] == ["335", 0]
    assert prompt["312"]["inputs"]["audio"] == ["303", 0]
    assert "subtitles" in prompt["314"]["inputs"]["text"]
    assert "text overlay" in prompt["314"]["inputs"]["text"]
    assert prompt["999"]["inputs"]["filename_prefix"] == "test_ltx_native"


def test_ltx_frame_count_aligns_to_video_vae_stride(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v")
    client = ComfyClient(settings)

    frame_count = client.ltx_frame_count(duration=3.2, fps=24)

    assert frame_count == 81
    assert (frame_count - 1) % 8 == 0
    assert frame_count >= 3.2 * 24


def test_ltx_fast_profile_skips_quality_lora(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v", ltx_profile="fast", ltx_model_format="checkpoint")
    workflow = ComfyClient(settings)._ltx_ia2v_workflow(
        image_name="avatar.png",
        audio_name="voice.wav",
        prompt="natural talking avatar",
        video_prefix="test_ltx",
        duration=1.0,
        seed=123,
        width=768,
        height=768,
        fps=24,
    )
    prompt = workflow["prompt"]

    assert prompt["317"]["inputs"]["ckpt_name"] == settings.ltx_fast_checkpoint
    assert "293" not in prompt
    assert prompt["290"]["inputs"]["model"] == ["317", 0]
    assert prompt["315"]["inputs"]["model"] == ["317", 0]


def test_ltx_gguf_workflow_uses_split_loaders(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v", ltx_model_format="gguf")
    workflow = ComfyClient(settings)._ltx_ia2v_workflow(
        image_name="avatar.png",
        audio_name="voice.wav",
        prompt="natural talking avatar",
        video_prefix="test_ltx",
        duration=1.0,
        seed=123,
        width=512,
        height=512,
        fps=24,
    )
    prompt = workflow["prompt"]

    assert prompt["317"]["class_type"] == "UnetLoaderGGUF"
    assert prompt["317"]["inputs"]["unet_name"] == settings.ltx_gguf_model
    assert prompt["318"]["class_type"] == "DualCLIPLoader"
    assert prompt["318"]["inputs"]["clip_name1"] == settings.ltx_text_encoder
    assert prompt["318"]["inputs"]["clip_name2"] == settings.ltx_text_projection
    assert prompt["318"]["inputs"]["type"] == "ltxv"
    assert prompt["335"]["class_type"] == "VAELoaderKJ"
    assert prompt["335"]["inputs"]["vae_name"] == settings.ltx_audio_vae
    assert prompt["336"]["class_type"] == "VAELoaderKJ"
    assert prompt["336"]["inputs"]["vae_name"] == settings.ltx_video_vae
    assert prompt["293"]["inputs"]["model"] == ["317", 0]
    assert prompt["290"]["inputs"]["model"] == ["293", 0]
    assert prompt["295"]["inputs"]["vae"] == ["336", 0]
    assert prompt["316"]["inputs"]["vae"] == ["336", 0]
    assert prompt["328"]["inputs"]["audio_vae"] == ["335", 0]
    assert prompt["303"]["inputs"]["audio_vae"] == ["335", 0]


def test_ltx_unet_workflow_uses_split_loaders(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v", ltx_model_format="unet")
    workflow = ComfyClient(settings)._ltx_ia2v_workflow(
        image_name="avatar.png",
        audio_name="voice.wav",
        prompt="natural talking avatar",
        video_prefix="test_ltx",
        duration=1.0,
        seed=123,
        width=512,
        height=512,
        fps=24,
    )
    prompt = workflow["prompt"]

    assert prompt["317"]["class_type"] == "UNETLoader"
    assert prompt["317"]["inputs"]["unet_name"] == settings.ltx_unet_model
    assert prompt["317"]["inputs"]["weight_dtype"] == settings.ltx_unet_weight_dtype
    assert prompt["318"]["class_type"] == "DualCLIPLoader"
    assert prompt["335"]["class_type"] == "VAELoaderKJ"
    assert prompt["336"]["class_type"] == "VAELoaderKJ"
    assert prompt["293"]["inputs"]["model"] == ["317", 0]
    assert prompt["295"]["inputs"]["vae"] == ["336", 0]
    assert prompt["328"]["inputs"]["audio_vae"] == ["335", 0]


def test_ltx_output_size_is_square_from_shorter_config_side(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", ltx_width=1280, ltx_height=720)

    assert VideoGenerationModule(settings).ltx_output_size() == 720


def test_ltx_output_size_uses_requested_resolution(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", ltx_width=1280, ltx_height=720)

    assert VideoGenerationModule(settings).ltx_output_size(512) == 512
    assert VideoGenerationModule(settings).ltx_output_size(513) == 512
    assert VideoGenerationModule(settings).ltx_output_size(120) == 256


def test_ltx_unload_after_video_can_keep_comfy_models_resident(monkeypatch, tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        comfy_input_dir=tmp_path / "input",
        comfy_output_dir=tmp_path / "output",
        ltx_unload_after_video=False,
    )
    client = ComfyClient(settings)
    avatar = tmp_path / "avatar.png"
    audio = tmp_path / "voice.wav"
    source_video = tmp_path / "source.mp4"
    avatar.write_bytes(b"avatar")
    audio.write_bytes(b"audio")
    source_video.write_bytes(b"video")
    free_called = False

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"prompt_id": "prompt_test"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            return FakeResponse()

    async def fake_poll(prompt_id, run_state=None):
        return {}

    async def fake_free_memory():
        nonlocal free_called
        free_called = True

    monkeypatch.setattr("app.services.comfy.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(client, "_poll", fake_poll)
    monkeypatch.setattr(client, "_find_video", lambda outputs: source_video)
    monkeypatch.setattr(client, "free_memory", fake_free_memory)

    result = asyncio.run(
        client.generate_ltx_ia2v(
            image_path=avatar,
            audio_path=audio,
            prompt="talking avatar",
            audio_duration=1.0,
            run_id="run_test",
            run_dir=tmp_path,
        )
    )

    assert result.read_bytes() == b"video"
    assert not free_called
