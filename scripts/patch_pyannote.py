#!/usr/bin/env python3
"""Патч pyannote.audio 3.3.x для совместимости с torchaudio >= 2.10 и huggingface_hub >= 1.0.

Проблемы:
1. torchaudio 2.10 удалил AudioMetaData, list_audio_backends, info()
2. huggingface_hub >= 1.0 убрал параметр use_auth_token (теперь token)

Этот скрипт патчит исходники pyannote в site-packages.
"""
import site
from pathlib import Path


def get_pyannote_dir() -> Path:
    for sp in site.getsitepackages():
        p = Path(sp) / "pyannote" / "audio"
        if p.exists():
            return p
    raise FileNotFoundError("pyannote.audio не найден в site-packages")


def patch_file(filepath: Path, replacements: list[tuple[str, str]]):
    text = filepath.read_text()
    original = text
    for old, new in replacements:
        text = text.replace(old, new)
    if text != original:
        filepath.write_text(text)
        print(f"  Пропатчен: {filepath.name}")
        return True
    else:
        print(f"  Без изменений: {filepath.name}")
        return False


def main():
    pyannote_dir = get_pyannote_dir()
    print(f"pyannote.audio: {pyannote_dir}\n")

    # === 1. Патч torchaudio совместимости ===
    print("=== Патч torchaudio совместимости ===")

    # core/io.py
    io_py = pyannote_dir / "core" / "io.py"
    patch_file(io_py, [
        (") -> torchaudio.AudioMetaData:", ") -> object:"),
        ("info : torchaudio.AudioMetaData", "info : object"),
        (
            """    if not backend:
        backends = (
            torchaudio.list_audio_backends()
        )  # e.g ['ffmpeg', 'soundfile', 'sox']
        backend = "soundfile" if "soundfile" in backends else backends[0]

    info = torchaudio.info(file["audio"], backend=backend)""",
            """    if not backend:
        backends = torchaudio.list_audio_backends() if hasattr(torchaudio, "list_audio_backends") else ["soundfile"]
        backend = "soundfile" if "soundfile" in backends else backends[0]

    if hasattr(torchaudio, "info"):
        info = torchaudio.info(file["audio"], backend=backend)
    else:
        import soundfile as sf
        _path = file["audio"] if isinstance(file["audio"], (str, Path)) else file["audio"].name
        sf_info = sf.info(_path)
        from types import SimpleNamespace
        info = SimpleNamespace(sample_rate=sf_info.samplerate, num_frames=sf_info.frames, num_channels=sf_info.channels, bits_per_sample=16, encoding="PCM_S")"""
        ),
        (
            """        if not backend:
            backends = (ы
                torchaudio.list_audio_backends()
            )  # e.g ['ffmpeg', 'soundfile', 'sox']
            backend = "soundfile" if "soundfile" in backends else backends[0]""",
            """        if not backend:
            backends = torchaudio.list_audio_backends() if hasattr(torchaudio, "list_audio_backends") else ["soundfile"]
            backend = "soundfile" if "soundfile" in backends else backends[0]"""
        ),
    ])

    # tasks/segmentation/mixins.py
    mixins_py = pyannote_dir / "tasks" / "segmentation" / "mixins.py"
    if mixins_py.exists():
        patch_file(mixins_py, [
            (
                "from torchaudio import AudioMetaData",
                "try:\n    from torchaudio import AudioMetaData\nexcept ImportError:\n    from types import SimpleNamespace as AudioMetaData"
            ),
        ])

    # utils/protocol.py
    protocol_py = pyannote_dir / "utils" / "protocol.py"
    if protocol_py.exists():
        patch_file(protocol_py, [
            (
                "torchaudio.list_audio_backends()",
                "(torchaudio.list_audio_backends() if hasattr(torchaudio, 'list_audio_backends') else ['soundfile'])"
            ),
        ])

    # === 2. Патч use_auth_token → token для huggingface_hub >= 1.0 ===
    print("\n=== Патч use_auth_token → token ===")

    count = 0
    for py_file in pyannote_dir.rglob("*.py"):
        text = py_file.read_text()
        if "use_auth_token" not in text:
            continue

        new_text = text
        # Replace parameter passing: use_auth_token=xxx → token=xxx
        # But keep the parameter name in function signatures and docstrings as-is,
        # only fix the actual calls to huggingface_hub functions
        import re

        # Replace in function calls: use_auth_token=use_auth_token → token=use_auth_token
        new_text = re.sub(
            r'(\w+)\(([^)]*?)use_auth_token=(use_auth_token|self\.use_auth_token)',
            lambda m: m.group(0).replace('use_auth_token=' + m.group(3), 'token=' + m.group(3)),
            new_text
        )

        # Replace use_auth_token=YOUR_AUTH_TOKEN in comments/docstrings
        new_text = new_text.replace('use_auth_token=YOUR_AUTH_TOKEN', 'token=YOUR_AUTH_TOKEN')

        if new_text != text:
            py_file.write_text(new_text)
            print(f"  Пропатчен: {py_file.relative_to(pyannote_dir)}")
            count += 1

    print(f"\n  Всего файлов пропатчено (use_auth_token): {count}")

    # Also patch the params dict key
    # In pipeline.py: params.setdefault("use_auth_token", use_auth_token)
    pipeline_py = pyannote_dir / "core" / "pipeline.py"
    if pipeline_py.exists():
        text = pipeline_py.read_text()
        new_text = text.replace(
            'params.setdefault("use_auth_token", use_auth_token)',
            'params.setdefault("token", use_auth_token)'
        )
        # Also fix the dict access in other places
        new_text = new_text.replace(
            '"use_auth_token"',
            '"token"'
        )
        if new_text != text:
            pipeline_py.write_text(new_text)
            print(f"  Дополнительно пропатчен: pipeline.py (dict keys)")

    # getter.py: model.setdefault("use_auth_token", ...)
    getter_py = pyannote_dir / "pipelines" / "utils" / "getter.py"
    if getter_py.exists():
        text = getter_py.read_text()
        new_text = text.replace(
            'model.setdefault("use_auth_token", use_auth_token)',
            'model.setdefault("token", use_auth_token)'
        )
        if new_text != text:
            getter_py.write_text(new_text)
            print(f"  Дополнительно пропатчен: getter.py (dict keys)")

    print("\nГотово!")


if __name__ == "__main__":
    main()
