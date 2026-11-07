"""Explicit public weight download, never performed by the API or on live calls."""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from backend.app.voice.open_speech_catalog import CHATTERBOX, CHATTERBOX_FILES, KOKORO, KOKORO_FILES, PARAKEET


def main():
    from huggingface_hub import snapshot_download

    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["asr", "tts"], required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--proof", required=True)
    parser.add_argument("--transport", choices=["hub", "urllib"], default="hub")
    parser.add_argument("--tts-backend", choices=["chatterbox", "kokoro"], default="chatterbox")
    args = parser.parse_args()
    artifact = PARAKEET if args.role == "asr" else (KOKORO if args.tts_backend == "kokoro" else CHATTERBOX)
    patterns = (list(KOKORO_FILES) if args.tts_backend == "kokoro" else list(CHATTERBOX_FILES)) if args.role == "tts" else ["*.json", "*.model", "model.safetensors"]
    if args.transport == "urllib":
        # Public HTTPS fallback for environments whose Hub/Xet transfer stalls.
        # Only exact, metadata-verified files are committed to the pinned cache.
        import fnmatch
        api = "https://huggingface.co/api/models/" + artifact.model_id + "/revision/" + artifact.revision + "?blobs=true"
        metadata = json.load(urllib.request.urlopen(api, timeout=30))
        assert metadata["sha"] == artifact.revision
        path = Path(args.cache_dir) / ("models--" + artifact.model_id.replace("/", "--")) / "snapshots" / artifact.revision
        path.mkdir(parents=True, exist_ok=True)
        for item in metadata["siblings"]:
            name = item["rfilename"]
            if Path(name).is_absolute() or ".." in Path(name).parts or not any(fnmatch.fnmatch(name, pattern) for pattern in patterns + ["LICENSE*", "README.md"]):
                continue
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = (item.get("lfs") or {}).get("sha256")
            if target.is_file() and expected:
                with target.open("rb") as handle:
                    if hashlib.file_digest(handle, "sha256").hexdigest() == expected:
                        continue
            temporary = target.with_name(target.name + ".partial")
            url = "https://huggingface.co/" + artifact.model_id + "/resolve/" + artifact.revision + "/" + name + "?download=true"
            with urllib.request.urlopen(url, timeout=30) as response, temporary.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
            with temporary.open("rb") as handle:
                actual = hashlib.file_digest(handle, "sha256").hexdigest()
            if expected and actual != expected:
                raise RuntimeError("Public model weight checksum mismatch")
            if item.get("size") is not None and temporary.stat().st_size != item["size"]:
                raise RuntimeError("Public model artifact size mismatch")
            temporary.replace(target)
            print(json.dumps({"artifact": name, "bytes": target.stat().st_size, "sha256": actual}), flush=True)
    else:
        path = Path(snapshot_download(artifact.model_id, revision=artifact.revision,
                    allow_patterns=patterns + ["LICENSE*", "README.md"], cache_dir=args.cache_dir,
                    token=False, max_workers=2))
    hashes = {}
    for file in path.rglob("*"):
        if file.is_file():
            with file.open("rb") as handle:
                hashes[file.relative_to(path).as_posix()] = hashlib.file_digest(handle, "sha256").hexdigest()
    proof = {"model_id": artifact.model_id, "revision": artifact.revision,
             "license": artifact.license_id, "sha256": hashes}
    Path(args.proof).write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps({"model": artifact.model_id, "revision": artifact.revision, "files": len(hashes)}))


if __name__ == "__main__":
    main()
