"""The encoder selects a native extension dynamically for the host CPU."""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("astc_encoder")
