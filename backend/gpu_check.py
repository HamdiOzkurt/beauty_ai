
import torch
import os
import platform

print("="*50)
print("GPU ve PyTorch Kurulum Teşhis Raporu")
print("="*50)

print(f"İşletim Sistemi: {platform.system()} {platform.release()}")
print(f"Python Sürümü: {platform.python_version()}")
print(f"PyTorch Sürümü: {torch.__version__}")

print("\n--- CUDA Bilgileri ---")
is_available = torch.cuda.is_available()
print(f"CUDA Kullanılabilir mi? (torch.cuda.is_available()): {is_available}")

if is_available:
    try:
        device_count = torch.cuda.device_count()
        print(f"Bulunan GPU Sayısı: {device_count}")
        
        # PyTorch'un hangi CUDA ve cuDNN versiyonları ile DERLENDİĞİNİ gösterir
        print(f"PyTorch için Derlenmiş CUDA Sürümü: {torch.version.cuda}")
        print(f"PyTorch için Derlenmiş cuDNN Sürümü: {torch.version.cudnn}")
        
        print("\n--- Aktif GPU Bilgileri ---")
        for i in range(device_count):
            print(f"  GPU {i}:")
            print(f"    Adı: {torch.cuda.get_device_name(i)}")
            print(f"    Compute Capability: {torch.cuda.get_device_capability(i)}")
            total_mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
            print(f"    Toplam Bellek: {total_mem:.2f} GB")
    except Exception as e:
        print(f"\n❌ GPU bilgileri alınırken bir hata oluştu: {e}")
        print("   Bu durum, sürücü ve toolkit arasında bir uyuşmazlık olduğunu gösterebilir.")

else:
    print("\n⚠️ PyTorch, sisteminizde kullanılabilir bir CUDA kurulumu bulamadı.")
    print("   NVIDIA sürücülerinizin ve CUDA Toolkit'inizin doğru şekilde kurulduğundan emin olun.")
    print("   Eğer sadece CPU kullanmak istiyorsanız bu bir sorun değildir.")

print("\n--- Ortam Değişkenleri (Path) ---")
path_var = os.environ.get('PATH', '')
path_list = path_var.split(os.pathsep)
cuda_paths = [p for p in path_list if 'cuda' in p.lower() or 'nvidia' in p.lower()]
if cuda_paths:
    print("PATH içinde bulunan CUDA/NVIDIA yolları:")
    for p in cuda_paths:
        print(f"  - {p}")
else:
    print("PATH ortam değişkeninizde 'cuda' veya 'nvidia' içeren bir yol bulunamadı.")
    print("Bu, DLL'lerin bulunamamasının bir nedeni olabilir.")


print("\n" + "="*50)
print("SONRAKİ ADIMLAR:")
print("1. Bu betiğin çıktısını kopyalayın.")
print("2. Terminalinize `nvidia-smi` komutunu yazın ve çalıştırın.")
print("3. Hem bu betiğin çıktısını hem de `nvidia-smi` komutunun çıktısını bana gönderin.")
print("="*50)
