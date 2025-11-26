"""
KRITIK: Bu modül tüm backend importlarından ÖNCE import edilmelidir!
cuDNN ve CUDA DLL'lerini Windows PATH'ine ekler.
"""
import os
import sys


def setup_cuda_environment():
    """CUDA/cuDNN DLL yollarını sisteme ekle - IMPORT EDİLMEDEN ÖNCE ÇALIŞMALI"""
    
    def add_dll_path(path):
        """DLL yolunu PATH ve DLL directory'ye ekle"""
        if not path or not os.path.isdir(path):
            return
        
        # PATH'e ekle
        current_path = os.environ.get("PATH", "")
        if path not in current_path:
            os.environ["PATH"] = path + os.pathsep + current_path
        
        # DLL directory'ye ekle (Windows 10+)
        try:
            os.add_dll_directory(path)
        except (OSError, AttributeError):
            pass
    
    # 1) cuDNN - EN YÜKSEK ÖNCELİK!
    try:
        import nvidia.cudnn
        cudnn_bin = os.path.join(nvidia.cudnn.__path__[0], "bin")
        add_dll_path(cudnn_bin)
    except Exception:
        pass
    
    # 2) cuBLAS
    try:
        import nvidia.cublas
        cublas_bin = os.path.join(nvidia.cublas.__path__[0], "bin")
        add_dll_path(cublas_bin)
    except Exception:
        pass
    
    # 3) PyTorch
    try:
        import torch
        torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        add_dll_path(torch_lib)
    except Exception:
        pass


# Modül import edildiğinde otomatik çalışsın
setup_cuda_environment()
