"""
Tek seferlik DLL kopyalama scripti
ctranslate2'yi import etmeden önce çalıştırılmalı
"""
import os
import shutil
import glob

print("=" * 60)
print("cuDNN DLL Kopyalama Scripti")
print("=" * 60)

try:
    # cuDNN bin klasörünü bul
    import nvidia.cudnn
    cudnn_bin = os.path.join(nvidia.cudnn.__path__[0], "bin")
    print(f"\ncuDNN bin: {cudnn_bin}")
    
    # ctranslate2 klasörünü bul (import etmeden!)
    import sys
    for path in sys.path:
        ct2_path = os.path.join(path, "ctranslate2")
        if os.path.isdir(ct2_path):
            print(f"ctranslate2: {ct2_path}")
            
            # TÜM cuDNN DLL'lerini kopyala
            dll_files = glob.glob(os.path.join(cudnn_bin, "cudnn*.dll"))
            print(f"\nKopyalanacak {len(dll_files)} DLL bulundu:")
            
            copied = 0
            for src in dll_files:
                dll_name = os.path.basename(src)
                dst = os.path.join(ct2_path, dll_name)
                
                if not os.path.isfile(dst):
                    try:
                        shutil.copy2(src, dst)
                        print(f"  ✅ {dll_name}")
                        copied += 1
                    except Exception as e:
                        print(f"  ❌ {dll_name}: {e}")
                else:
                    print(f"  ⏭️  {dll_name} (zaten var)")
            
            print(f"\n✅ {copied} DLL kopyalandı!")
            print(f"📁 Hedef: {ct2_path}")
            break
    else:
        print("❌ ctranslate2 bulunamadı!")
        
except Exception as e:
    print(f"❌ Hata: {e}")
    import traceback
    traceback.print_exc()

print("=" * 60)
