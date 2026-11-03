# -*- mode: python ; coding: utf-8 -*-
# Build: set DICHVIET_MODE=onefile (1 file exe) hoặc onedir (bản portable)
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules, collect_data_files

ROOT = os.path.abspath(SPECPATH)
NAME = 'Dich Viet by Duy Anh'
MODE = os.environ.get('DICHVIET_MODE', 'onefile')
EXCLUDES = [
    'torch', 'torchvision', 'torchaudio', 'functorch', 'tensorflow', 'tensorboard', 'keras', 'tf_keras',
    'transformers', 'safetensors', 'jax', 'jaxlib', 'onnx', 'hf_xet', 'pydantic_core',
    'triton', 'numba', 'llvmlite', 'scipy', 'sklearn', 'pandas', 'matplotlib', 'cv2', 'sympy',
    'IPython', 'jupyter', 'notebook', 'pytest', 'pydantic', 'rich', 'pygments', 'jinja2', 'cryptography',
    'tkinter', 'opennmt', 'fairseq', 'sacremoses', 'spacy', 'nltk', 'playwright', 'PyQt5', 'PyQt6',
    'PySide2', 'PySide6', 'wx', 'gi', 'h5py', 'grpc', 'boto3', 'botocore', 'sqlalchemy',
]
binaries = collect_dynamic_libs('ctranslate2') + collect_dynamic_libs('av') + collect_dynamic_libs('onnxruntime')
datas = [(os.path.join(ROOT, 'ui.html'), '.')] + collect_data_files('reportlab') + \
    collect_data_files('faster_whisper') + collect_data_files('opencc')

a = Analysis(
    [os.path.join(ROOT, 'dich_viet.py')],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=['ctranslate2', 'sentencepiece', 'pypdf', 'av', 'onnxruntime', 'tokenizers', 'opencc', 'numpy'] +
        collect_submodules('faster_whisper') + collect_submodules('reportlab', filter=lambda m: not m.startswith(('reportlab.graphics', 'reportlab.lib.testutils'))),
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
common = dict(name=NAME, debug=False, strip=False, upx=False, console=False,
              icon=[os.path.join(ROOT, 'logo.ico')], version=os.path.join(ROOT, 'version_info.txt'))
if MODE == 'onefile':
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NAME)
