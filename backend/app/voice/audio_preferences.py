"""Apply the called company's saved settings, never caller-supplied metadata."""
from backend.app.services.voice_onboarding_service import stored_business_profile
from backend.app.voice.adapters import OpenAIAudioConfig


def phone_audio_config(db, settings, config):
    business = stored_business_profile(db, config.company_id)
    noise = business.get("input_noise_reduction", "off")
    if noise not in {"off", "near_field", "far_field"}:
        noise = "off"
    # Older API versions allowed 2x. Preserve the record, but stay within the
    # Realtime provider's supported range; new customization writes reject >1.5.
    speed = min(1.5, max(0.5, float(getattr(config, "speech_speed", 1.0) or 1.0)))
    styles = {"professionnel": "professional", "chaleureux": "warm and welcoming",
              "dynamique": "energetic", "calme": "calm", "elegant": "polished"}
    return OpenAIAudioConfig(
        api_key=settings.openai_api_key, stt_model=settings.voice_stt_model,
        tts_model=settings.voice_tts_model,
        tts_voice=getattr(config, "voice_id", None) or settings.voice_tts_voice or "alloy",
        speech_speed=speed, input_noise_reduction=noise,
        delivery_style=styles.get(getattr(config, "personality_tone", ""), "professional"),
    )
