"""The texture decoder's CPU detection reads these JSON tables at runtime."""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("archspec")
