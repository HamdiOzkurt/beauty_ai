"""
Windows DLL preload fix - ctranslate2 için cuDNN DLL'lerini önceden yükle
"""
import os
import sys
import ctypes

def preload_cudnn_dlls():
    """cuDNN DLL'lerini manuel olarak önceden yükle"""
    
    try:
        import nvidia.cudnn
        cudnn_bin = os.path.join(nvidia.cudnn.__path__[0], "bin")
        
        # Kritik DLL'leri sırayla yükle
        critical_dlls = [
            "cudnn64_9.dll",
            "cudnn_ops64_9.dll", 
            "cudnn_cnn64_9.dll",
            "cudnn_adv64_9.dll",
            "cudnn_graph64_9.dll",
            "cudnn_engines_precompiled64_9.dll",
            "cudnn_engines_runtime_compiled64_9.dll",
            "cudnn_heuristic64_9.dll"
        ]
        
        loaded = []
        failed = []
        
        for dll_name in critical_dlls:
            dll_path = os.path.join(cudnn_bin, dll_name)
            if os.path.isfile(dll_path):
                try:
                    # DLL'i global namespace'e yükle
                    handle = ctypes.CDLL(dll_path, winmode=0)  # RTLD_GLOBAL yerine winmode
                    loaded.append(dll_name)
                except Exception as e:
                    failed.append(f"{dll_name}: {str(e)[:50]}")
            else:
                failed.append(f"{dll_name}: Dosya bulunamadı")
        
        if loaded:
            print(f"✅ {len(loaded)} cuDNN DLL önceden yüklendi")
        if failed and len(failed) < len(critical_dlls):
            print(f"⚠️ {len(failed)} DLL yüklenemedi (sorun değil)")
                
        return len(loaded) > 0
        
    except ImportError:
        # nvidia paketi yok, sessizce devam et
        return False
    except Exception as e:
        print(f"⚠️ cuDNN preload uyarısı: {str(e)[:50]}")
        return False


# Modül import edildiğinde otomatik çalış
preload_cudnn_dlls()
