# Beauty Voice Assistant

Bu proje, bir güzellik merkezi için sesli asistan ve randevu yönetim sistemi içerir.

## Kurulum

1.  Proje dosyalarını bilgisayarınıza klonlayın.
2.  Gerekli Python kütüphanelerini yükleyin:

    ```bash
    pip install -r backend/requirements.txt
    ```

3.  `.env.example` dosyasını `.env` olarak kopyalayın ve gerekli ortam değişkenlerini ayarlayın.

## Kullanım

1.  Veritabanı ve web sunucusunu başlatmak için:

    ```bash
    docker-compose up -d
    ```

2.  MCP sunucusunu başlatın:

    ```bash
    start_mcp_server.bat
    ```

3.  Web sunucusunu başlatın:

    ```bash
    start_web_server.bat
    ```

Uygulama şimdi `http://localhost:8000` adresinde çalışıyor olmalıdır.
