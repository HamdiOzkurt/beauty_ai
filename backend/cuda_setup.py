"""
KRITIK: Bu modül tüm backend importlarından ÖNCE import edilmelidir!
cuDNN ve CUDA DLL'lerini Windows PATH'ine ekler.
"""
import os
import sys


def setup_cuda_environment():
    """CUDA/cuDNN DLL yollarını sisteme ekle - IMPORT EDİLMEDEN ÖNCE ÇALIŞMALI"""
    
    def add_dll_path(path, priority=False):
        """DLL yolunu PATH ve DLL directory'ye ekle"""
        if not path or not os.path.isdir(path):
            return
        
        # PATH'e ekle (priority=True ise başa ekle, yoksa sona)
        current_path = os.environ.get("PATH", "")
        if path not in current_path:
            if priority:
                os.environ["PATH"] = path + os.pathsep + current_path
            else:
                os.environ["PATH"] = current_path + os.pathsep + path
        
        # DLL directory'ye ekle (Windows 10+)
        try:
            os.add_dll_directory(path)
        except (OSError, AttributeError):
            pass
    
    # 1) CUDA Runtime (en yüksek öncelik)
    try:
        import nvidia.cuda_runtime
        cuda_runtime_bin = os.path.join(nvidia.cuda_runtime.__path__[0], "bin")
        add_dll_path(cuda_runtime_bin, priority=True)
    except Exception:
        pass
    
    # 2) cuBLAS (cuDNN'den önce!)
    try:
        import nvidia.cublas
        cublas_bin = os.path.join(nvidia.cublas.__path__[0], "bin")
        add_dll_path(cublas_bin, priority=True)
    except Exception:
        pass
    
    # 3) cuDNN - EN YÜKSEK ÖNCELİK!
    try:
        import nvidia.cudnn
        cudnn_bin = os.path.join(nvidia.cudnn.__path__[0], "bin")
        add_dll_path(cudnn_bin, priority=True)
    except Exception:
        pass
    
    # 4) PyTorch (en son, düşük öncelik)
    # PyTorch kendi cuDNN'ini değil nvidia-cudnn-cu12'yi kullansın
    try:
        import torch
        torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        add_dll_path(torch_lib, priority=False)
    except Exception:
        pass


# Modül import edildiğinde otomatik çalışsın
setup_cuda_environment()
