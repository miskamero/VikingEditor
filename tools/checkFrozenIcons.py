import io
from pathlib import Path
import sys


def main():
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Run the PyInstaller-built checkFrozenIcons executable.")

    from UnityPy.export import SpriteHelper
    from fmod_toolkit.importer import get_fmod_path_for_system
    from PIL import Image

    library = Path(get_fmod_path_for_system())
    assert library.is_file(), f"Missing FMOD library: {library}"
    assert library.is_relative_to(Path(sys._MEIPASS)), library
    assert callable(SpriteHelper.get_image_from_sprite)
    image = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    with Image.open(buffer) as decoded:
        assert decoded.getpixel((0, 0)) == (255, 0, 0, 128)
    print("PASS: frozen UnityPy sprite imports, bundled FMOD DLL, and PNG encoding")


if __name__ == "__main__":
    main()
