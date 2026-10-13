"""Read-only model permission check. Does not create a session or generate audio."""
import re,httpx
class VoiceRealtimeReadiness:
    def __init__(self,settings):self.settings=settings
    async def validate_model(self):
        model=self.settings.voice_realtime_model or ""
        if not self.settings.openai_api_key or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}",model):return False
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r=await c.get("https://api.openai.com/v1/models/"+model,headers={"Authorization":"Bearer "+self.settings.openai_api_key})
                return r.status_code==200 and r.json().get("id")==model
        except (httpx.HTTPError,ValueError):return False
