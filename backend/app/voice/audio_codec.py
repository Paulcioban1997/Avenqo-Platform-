"""Shared Telnyx G.711/PCM conversion used by live media and offline evaluation."""
import array
import audioop
import base64
import binascii


class InvalidMediaFrame(ValueError):
    pass


class TelnyxAudioCodec:
    def __init__(self) -> None:
        self._input_state = None
        self._output_state = None

    def reset(self) -> None:
        self._input_state = None
        self._output_state = None

    @staticmethod
    def decode_payload(payload: object, maximum: int) -> bytes:
        if not isinstance(payload, str) or len(payload) > ((maximum + 2) // 3) * 4:
            raise InvalidMediaFrame("Invalid audio payload")
        try:
            raw = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error):
            raise InvalidMediaFrame("Invalid audio payload") from None
        if not raw or len(raw) > maximum:
            raise InvalidMediaFrame("Invalid audio payload")
        return raw

    def inbound_pcm(self, payload: object) -> bytes:
        raw = self.decode_payload(payload, 1600)
        pcm = audioop.ulaw2lin(raw, 2)
        converted, self._input_state = audioop.ratecv(pcm, 2, 1, 8000, 24000, self._input_state)
        return converted

    @staticmethod
    def _anti_alias_filter(pcm: bytes) -> bytes:
        """7-tap symmetric FIR low-pass filter (cutoff ~3600 Hz at 24000 Hz).
        Attenuates energy above 4 kHz before 3:1 downsampling, preventing severe harmonic aliasing.
        """
        if len(pcm) < 16:
            return pcm
        samples = array.array("h", pcm)
        n = len(samples)
        out = array.array("h", [0] * n)
        # Scaled coefficients [36, 97, 195, 368, 195, 97, 36] / 1024
        for i in range(3, n - 3):
            val = (
                36 * (samples[i - 3] + samples[i + 3])
                + 97 * (samples[i - 2] + samples[i + 2])
                + 195 * (samples[i - 1] + samples[i + 1])
                + 368 * samples[i]
            ) >> 10
            out[i] = max(-32768, min(32767, val))
        for i in (0, 1, 2):
            out[i] = samples[i]
        for i in (n - 3, n - 2, n - 1):
            out[i] = samples[i]
        return out.tobytes()

    def outbound_pcm(self, payload: object) -> bytes:
        pcm = self.decode_payload(payload, 48000)
        if len(pcm) % 2:
            raise InvalidMediaFrame("Invalid PCM frame")
        filtered = self._anti_alias_filter(pcm)
        converted, self._output_state = audioop.ratecv(filtered, 2, 1, 24000, 8000, self._output_state)
        return audioop.lin2ulaw(converted, 2)
