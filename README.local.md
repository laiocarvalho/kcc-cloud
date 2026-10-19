# Rodar o KCC Cloud localmente

Este guia sobe o ambiente de desenvolvimento com Docker Compose: Next.js, API Flask, worker Celery e Redis.

O [README.md](README.md) descreve a imagem pronta de produção. Os passos abaixo usam o código deste repositório.

## Requisitos

- Docker Desktop no Windows ou macOS, ou Docker Engine com Compose no Linux
- Git
- Portas livres: `3000` (interface), `8060` (API) e `6379` (Redis)
- Cerca de 4 GB de RAM livres. O worker limita o uso a 3 GB

No Windows, abra o Docker Desktop e espere o engine Linux ficar pronto antes do `docker compose`.

## 1. Clonar e inicializar o KCC

O conversor fica no submodule `app/backend/app/kcc`. Sem ele, o build do backend falha.

```bash
git clone https://github.com/laiocarvalho/kcc-cloud.git
cd kcc-cloud
git submodule update --init --recursive
```

## 2. Variáveis de ambiente

```bash
# Windows (PowerShell)
copy .env.example .env

# Linux ou macOS
cp .env.example .env
```

O Compose lê esse arquivo. Para acesso nesta máquina, deixe:

```bash
NEXT_PUBLIC_API_URL=/api
NEXT_PUBLIC_WS_URL=http://localhost:8060
```

O Next.js não faz upgrade de WebSocket. O navegador fala com a API publicada em `localhost:8060`. Em outro computador da rede, troque `localhost` pelo IP desta máquina.

`PUID` e `PGID` são o usuário dentro do container Linux. `1000` funciona no Docker Desktop.

## 3. KindleGen (MOBI e AZW3)

EPUB, PDF e CBZ funcionam sem este binário. MOBI e AZW3 precisam do KindleGen Linux 2.9, que é um executável i386. A imagem de desenvolvimento já instala as bibliotecas de 32 bits.

Baixe o pacote e confira o SHA-256 `9828db5a2c8970d487ada2caa91a3b6403210d5d183a7e3849b1b206ff042296`. O binário extraído deve ter SHA-256 `b8b0f0ab83e74070119066bf4f3c56267e5ee43d2c2bac7091bb447e9f461a69`.

```powershell
New-Item -ItemType Directory -Force -Path volumes\kindlegen | Out-Null
Invoke-WebRequest -Uri "https://archive.org/download/kindlegen2.9/kindlegen_linux_2.6_i386_v2_9.tar.gz" -OutFile "$env:TEMP\kindlegen.tar.gz"
tar -xzf "$env:TEMP\kindlegen.tar.gz" -C "$env:TEMP" kindlegen
Copy-Item -Force "$env:TEMP\kindlegen" "volumes\kindlegen\kindlegen"
```

```bash
mkdir -p volumes/kindlegen
curl -L "https://archive.org/download/kindlegen2.9/kindlegen_linux_2.6_i386_v2_9.tar.gz" -o /tmp/kindlegen.tar.gz
tar -xzf /tmp/kindlegen.tar.gz -C volumes/kindlegen kindlegen
chmod +x volumes/kindlegen/kindlegen
```

O arquivo `volumes/kindlegen/kindlegen` fica de fora do Git. O Compose monta essa pasta em `/app/kindlegen`.

## 4. Subir

```bash
docker compose up -d --build
```

O primeiro build baixa a imagem Python, pacotes do Debian, dependências pip e o `pnpm install` do frontend. Pode levar vários minutos.

## 5. Abrir

- Interface: http://localhost:3000
- API: http://localhost:8060/health

A interface também encaminha `http://localhost:3000/api/...` para o backend.

## Operação

```bash
docker compose ps
docker compose logs -f
docker compose down
docker compose up -d --build
```

`docker compose down` para os containers e mantém os volumes de conversões e do Redis. Para apagar esses dados também, use `docker compose down -v`.

## Serviços

| Serviço | Container | Função |
| --- | --- | --- |
| `frontend-dev` | `kcc-cloud-frontend-dev` | Next.js em modo dev, porta 3000 |
| `backend` | `kcc-cloud-backend` | API Flask com Gunicorn, porta 8060 |
| `celery-worker` | `kcc-cloud-celery-worker-1` | Conversões KCC |
| `redis` | `kcc-cloud-redis` | Fila do Celery, porta 6379 |

O código em `app/frontend` e `app/backend/app` é montado nos containers. Alterações de Python e do frontend recarregam sem rebuild. Mudança de `Dockerfile`, `requirements.txt` ou `package.json` pede `docker compose up -d --build`.
