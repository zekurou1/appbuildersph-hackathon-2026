from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from pathlib import Path

project = Path(SPECPATH).parent
hidden = collect_submodules('omnifind') + collect_submodules('winrt')
data = collect_data_files('transformers') + collect_data_files('omnifind')
analysis = Analysis([str(project / 'packaging/cli_entry.py'), str(project / 'packaging/gui_entry.py')],
    pathex=[str(project)], binaries=[], datas=data, hiddenimports=hidden,
    excludes=['matplotlib', 'scipy', 'sklearn', 'tensorflow', 'torchaudio', 'torchvision',
              'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick'],
    noarchive=False)
archive = PYZ(analysis.pure)
cli_scripts = [entry for entry in analysis.scripts if entry[0] != 'gui_entry']
gui_scripts = [entry for entry in analysis.scripts if entry[0] != 'cli_entry']
cli = EXE(archive, cli_scripts, [], exclude_binaries=True, name='OmniFindCLI', console=True, upx=False)
gui = EXE(archive, gui_scripts, [], exclude_binaries=True, name='OmniFind', console=False, upx=False)
bundle = COLLECT(cli, gui, analysis.binaries, analysis.datas, strip=False, upx=False, name='OmniFindLocal')
