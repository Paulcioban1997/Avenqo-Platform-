"""Bounded public FLEURS test samples with human references, never customer audio."""
import argparse
import csv
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

FLEURS_REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"


def main():
    import soundfile as sf
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest = []
    for config, locale in [("fr_fr", "fr"), ("en_us", "en"), ("ro_ro", "ro")]:
        base = "https://huggingface.co/datasets/google/fleurs/resolve/" + FLEURS_REVISION + "/data/" + config + "/"
        tsv = urllib.request.urlopen(base + "test.tsv", timeout=30).read().decode("utf-8")
        rows = list(csv.reader(io.StringIO(tsv), delimiter="\t"))
        with urllib.request.urlopen(base + "audio/test.tar.gz", timeout=30) as response:
            with tarfile.open(fileobj=response, mode="r|gz") as archive:
                member = next(item for item in archive if item.isfile() and item.name.endswith(".wav"))
                if member.size > 3_000_000:
                    raise ValueError("Reference audio too large")
                audio = archive.extractfile(member).read()
                name = Path(member.name).name
        row = next(item for item in rows if name in item)
        samples, rate = sf.read(io.BytesIO(audio), dtype="float32")
        if samples.ndim != 1 or len(samples) > rate * 30:
            raise ValueError("Reference must be mono and at most 30 seconds")
        path = root / (locale + "-pcm16.wav")
        sf.write(path, samples, rate, subtype="PCM_16")
        manifest.append({"locale": locale, "path": str(path), "reference": row[2],
            "source": "google/fleurs@" + FLEURS_REVISION + ":" + config + ":test:" + name,
            "license": "CC-BY-4.0", "original_sha256": hashlib.sha256(audio).hexdigest(),
            "pcm16_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "transform": "Original recording converted to PCM16; no synthetic speech"})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"public_human_test_samples": len(manifest), "revision": FLEURS_REVISION}))


if __name__ == "__main__":
    main()
