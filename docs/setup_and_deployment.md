# Руководство по развёртыванию и базовой настройке

Данный документ содержит пошаговые инструкции по развёртыванию почтового AI-агента, управлению контейнерами, миграциям базы данных, наполнению учебными данными и проверке работоспособности.

---

## 1. Системные требования

### Минимальные требования:
- **ОС:** Windows 10/11 (с WSL2 и Docker Desktop) или Linux (Ubuntu 22.04+).
- **Python:** 3.12+ (проект использует современные языковые конструкции PEP 695).
- **Docker:** Docker Engine 24+ с плагином Docker Compose v2.
- **ОЗУ:**
  - При использовании локальных моделей Ollama: от **16 ГБ ОЗУ** (или GPU от 8 ГБ VRAM).
  - При использовании облачных API моделей (OpenAI / OpenRouter): от **4 ГБ ОЗУ**.

---

## 2. Быстрый автоматический запуск (Рекомендуемый)

Для быстрого старта подготовлены платформенные скрипты развёртывания (`setup.ps1` для Windows и `Makefile` / `scripts/setup.sh` для Linux и macOS), которые в автоматическом режиме:
1. Создают `.env` из `.env.example`, если файл конфигурации отсутствует.
2. Проверяют наличие и при необходимости переносят журнал `security_events.jsonl` в каталог `audit/`.
3. Поднимают независимые контейнеры локальных моделей (`embedder` и `llm`).
4. Собирают и запускают основной стек: PostgreSQL, RabbitMQ, FastAPI
   и независимые воркеры `document_indexing` и `email_indexing`.
5. Дожидаются готовности эндпоинта `/health` и доступности API моделей Ollama.
6. Скачивают веса моделей (`qwen3-embedding:0.6b` и `qwen2.5:7b`), если они ещё не загружены.
7. Применяют миграции Alembic и запускают наполнение учебными данными (`scripts.seed_data`).

### Команды запуска:

**Windows (PowerShell):**
```powershell
.\setup.ps1
```

**Linux / macOS:**
```bash
make setup
# или напрямую: sh scripts/setup.sh
```

После завершения работы скрипта сервис готов к работе:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Healthcheck:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 3. Ручной пошаговый запуск

Все компоненты системы разделены на независимые Docker Compose файлы, что позволяет гибко комбинировать локальный и облачный контуры.

### Шаг 1: Конфигурация окружения
Скопируйте файл с переменными окружения:
```bash
cp .env.example .env
```
При необходимости отредактируйте параметры подключения в `.env`:
- `DB_HOST`, `DB_PORT`, `DB_PASSWORD` — реквизиты PostgreSQL;
- `RABBITMQ_URL` — строка подключения к брокеру;
- `LLM_URL`, `EMBEDDING_URL` — точки подключения к моделям.

### Шаг 2: Запуск локальных моделей (Ollama)

* **Запуск локального эмбеддера (`Qwen3-Embedding-0.6B` на порту 11434):**
  ```bash
  docker compose -f docker-compose.embedder.yml up -d
  docker compose -f docker-compose.embedder.yml exec embedder ollama pull qwen3-embedding:0.6b
  ```

* **Запуск локальной LLM агента (`Qwen2.5:7b` на порту 11435):**
  ```bash
  docker compose -f docker-compose.llm.yml up -d
  docker compose -f docker-compose.llm.yml exec llm ollama pull qwen2.5:7b
  ```

> [!TIP]
> **Использование внешних облачных API:**  
> Если вы хотите использовать облачные модели (например, OpenAI GPT-4o-mini или модели через OpenRouter), не поднимайте `docker-compose.llm.yml`, а укажите в `.env`:
> ```env
> LLM_URL=https://openrouter.ai/api/v1/chat/completions
> LLM_MODEL=qwen/qwen-2.5-7b-instruct
> LLM_API_KEY=your_api_key_here
> ```

### Шаг 3: Запуск ядра системы
Запустите базу данных, брокер сообщений, сервис API и фоновый воркер:
```bash
docker compose up -d --build
```

### Шаг 4: Миграции и наполнение базы данных
При первом запуске выполните сидинг (создание учётных записей, заливка учебных писем, индексация регламентов):
```bash
docker compose exec api python -m scripts.seed_data
```

---

## 4. Управление пользователями и аутентификация

В системе реализован контроль доступа на основе ролей (**RBAC**):
- **`manager`** — имеет доступ к поиску писем, чтению цепочек, созданию черновиков и диалогу с AI-агентом (`/api/v1/agent/*`, `/api/v1/emails/*`, `/api/v1/drafts/*`).
- **`admin`** — имеет полный доступ, включая индексацию корпоративных документов (`/api/v1/admin/documents`) и аудит инцидентов безопасности (`/api/v1/admin/security/events`).

### Учётные данные по умолчанию:
- **Email:** `manager@example.org`
- **Пароль:** `AgentDemo-2026!`
- **Роль:** `manager`

### Создание нового пользователя:
Для создания дополнительных учётных записей воспользуйтесь CLI-скриптом:
```bash
docker compose exec api python -m scripts.create_user new_admin@company.ru --role admin --password "StrongPass2026!"
```

---

## 5. Вход через Swagger UI и проверка приёмки

1. Откройте в браузере: [http://localhost:8000/docs](http://localhost:8000/docs).
2. Нажмите зелёную кнопку **Authorize** в правом верхнем углу.
3. В открывшейся форме введите:
   - **Username:** `manager@example.org`
   - **Password:** `AgentDemo-2026!`
4. Нажмите **Authorize**, затем **Close**. Все последующие запросы в Swagger будут автоматически подписываться Bearer-токеном.

### Пример контрольного запроса:
Перейдите к ручке `POST /api/v1/agent/chat` и отправьте запрос:
```json
{
  "message": "Найди последнюю переписку с клиентом по проекту X, перечисли согласованные сроки и подготовь черновик ответа на его последнее письмо с учётом условий поставки"
}
```

Ожидаемый ответ содержит:
- `status`: `"completed"`;
- `draft_id`: UUID созданного черновика;
- `used_document_ids`: `["doc_delivery_terms"]`;
- `used_email_ids`: список идентификаторов писем Проекта X.

---

## 6. Запуск тестов

Для запуска полного набора из 80 автоматизированных тестов выполните:

**Внутри контейнера API:**
```bash
docker compose exec api pytest -v
```

**Локально в виртуальном окружении:**
```bash
.venv/Scripts/python.exe -m pytest -v
```
*(Для Linux: `.venv/bin/pytest -v`)*
