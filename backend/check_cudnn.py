import nvidia.cudnn
import ctranslate2
import os
import glob

print("=" * 60)
print("cuDNN DLL Kontrol Scripti")
print("=" * 60)

# 1) Kaynak kontrol
cudnn_bin = os.path.join(nvidia.cudnn.__path__[0], 'bin')
src = os.path.join(cudnn_bin, 'cudnn_ops64_9.dll')
print(f"\n1) cuDNN DLL kaynak: {src}")
print(f"   Var mi? {os.path.isfile(src)}")

# 2) Hedef kontrol
ct2_dir = os.path.dirname(ctranslate2.__file__)
dst = os.path.join(ct2_dir, 'cudnn_ops64_9.dll')
print(f"\n2) ctranslate2 hedef: {dst}")
print(f"   Var mi? {os.path.isfile(dst)}")

# 3) Tüm DLL'ler
print(f"\n3) cuDNN bin klasoru: {cudnn_bin}")
print("   DLL dosyalari:")
dll_files = glob.glob(os.path.join(cudnn_bin, '*.dll'))
for f in dll_files:
    print(f"   - {os.path.basename(f)}")

print("\n" + "=" * 60)
