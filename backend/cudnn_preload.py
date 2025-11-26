"""
Windows DLL preload fix - PyTorch ve ctranslate2 için cuDNN DLL'lerini önceden yükle
"""
import os
import sys
import ctypes

def preload_cudnn_dlls():
    """cuDNN DLL'lerini manuel olarak önceden yükle"""
    
    try:
        # 1. nvidia-cudnn-cu12 paketinden DLL'leri yükle
        import nvidia.cudnn
        cudnn_bin = os.path.join(nvidia.cudnn.__path__[0], "bin")
        
        # 2. nvidia-cublas-cu12 paketinden DLL'leri yükle (cuDNN bağımlılığı)
        try:
            import nvidia.cublas
            cublas_bin = os.path.join(nvidia.cublas.__path__[0], "bin")
            
            # cuBLAS DLL'lerini önce yükle (cuDNN'in bağımlılığı)
            cublas_dlls = [
                "cublas64_12.dll",
                "cublasLt64_12.dll"
            ]
            
            for dll_name in cublas_dlls:
                dll_path = os.path.join(cublas_bin, dll_name)
                if os.path.isfile(dll_path):
                    try:
                        ctypes.CDLL(dll_path, winmode=0x00000008)  # LOAD_WITH_ALTERED_SEARCH_PATH
                    except Exception:
                        pass
        except Exception:
            pass
        
        # 3. cuDNN DLL'lerini sırayla yükle
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
                    # DLL'i LOAD_WITH_ALTERED_SEARCH_PATH flag'i ile yükle
                    handle = ctypes.CDLL(dll_path, winmode=0x00000008)
                    loaded.append(dll_name)
                except Exception as e:
                    failed.append(f"{dll_name}: {str(e)[:50]}")
            else:
                failed.append(f"{dll_name}: Dosya bulunamadı")
        
        if loaded:
            print(f"[OK] {len(loaded)} cuDNN DLL onceden yuklendi")
        if failed and len(failed) < len(critical_dlls):
            print(f"[WARN] {len(failed)} DLL yuklenemedi (sorun degil)")
                
        return len(loaded) > 0
        
    except ImportError:
        # nvidia paketi yok, sessizce devam et
        return False
    except Exception as e:
        print(f"[WARN] cuDNN preload uyarisi: {str(e)[:50]}")
        return False


# Modül import edildiğinde otomatik çalış
preload_cudnn_dlls()
