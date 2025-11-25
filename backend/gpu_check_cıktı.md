GPU ve PyTorch Kurulum Teşhis Raporu
==================================================
İşletim Sistemi: Windows 11
Python Sürümü: 3.13.3
PyTorch Sürümü: 2.7.1+cpu

--- CUDA Bilgileri ---
CUDA Kullanılabilir mi? (torch.cuda.is_available()): False

⚠️ PyTorch, sisteminizde kullanılabilir bir CUDA kurulumu bulamadı.
   NVIDIA sürücülerinizin ve CUDA Toolkit'inizin doğru şekilde kurulduğundan emin olun.
   Eğer sadece CPU kullanmak istiyorsanız bu bir sorun değildir.

--- Ortam Değişkenleri (Path) ---
PATH içinde bulunan CUDA/NVIDIA yolları:
  - C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin
  - C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\libnvvp
  - C:\Program Files (x86)\NVIDIA Corporation\PhysX\Common
  - C:\Program Files\NVIDIA Corporation\NVIDIA app\NvDLISR
  - C:\Program Files\NVIDIA Corporation\Nsight Compute 2025.2.1\
  - C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin
  - C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\libnvvp
  - C:\Program Files (x86)\NVIDIA Corporation\PhysX\Common
  - C:\Program Files\NVIDIA Corporation\NVIDIA app\NvDLISR
  - C:\Program Files\NVIDIA Corporation\Nsight Compute 2025.2.1\
  - C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin

==================================================
SONRAKİ ADIMLAR:
1. Bu betiğin çıktısını kopyalayın.
2. Terminalinize `nvidia-smi` komutunu yazın ve çalıştırın.
3. Hem bu betiğin çıktısını hem de `nvidia-smi` komutunun çıktısını bana gönderin.
==================================================
PS C:\Users\hamdi\Desktop\Beauty-Salon-Assistant> 


(myenv) PS C:\Users\hamdi\Desktop\Beauty-Salon-Assistant> nvidia-smi
Tue Nov 25 14:01:18 2025       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 577.03                 Driver Version: 577.03         CUDA Version: 12.9     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                  Driver-Model | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 4050 ...  WDDM  |   00000000:01:00.0 Off |                  N/A |
| N/A   41C    P0             18W /  120W |       0MiB /   6141MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+