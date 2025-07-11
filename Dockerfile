# Imagem base com Python e Debian
FROM python:3.11-slim

# Instala dependências do sistema
RUN apt-get update && apt-get install -y     tesseract-ocr     libglib2.0-0     libsm6     libxext6     libxrender-dev     && rm -rf /var/lib/apt/lists/*

# Cria diretório da aplicação
WORKDIR /app

# Copia os arquivos
COPY . .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta
EXPOSE 10000

# Comando de start
CMD ["python", "app.py"]
