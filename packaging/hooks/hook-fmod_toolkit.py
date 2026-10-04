"""FMOD is loaded with ctypes from a package-relative platform directory."""
from PyInstaller.utils.hooks import collect_dynamic_libs

# Preserve fmod_toolkit/libfmod/Windows/x64/fmod.dll (or the host equivalent).
# Putting the DLL at the bundle root does not satisfy the toolkit's importer.
binaries = collect_dynamic_libs("fmod_toolkit")
