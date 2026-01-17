# Быстрый старт

## Установка и запуск

### Вариант 1: Автоматический запуск (рекомендуется)

```bash
cd web-interface
./start.sh
```

Скрипт автоматически:
- Установит зависимости backend и frontend
- Запустит backend на http://localhost:5000
- Запустит frontend на http://localhost:3000

### Вариант 2: Ручной запуск

#### Backend (в отдельном терминале):

```bash
cd web-interface/backend
pip install -r requirements.txt
python3 app.py
```

Backend будет доступен на http://localhost:5000

#### Frontend (в отдельном терминале):

```bash
cd web-interface/frontend
npm install
npm start
```

Frontend будет доступен на http://localhost:3000

## Использование

1. Откройте браузер и перейдите на http://localhost:3000
2. Выберите вкладку:
   - **Файлы** - просмотр распарсенных и нормализованных данных
   - **Управление** - запуск задач (скачивание, парсинг, нормализация)
   - **Сокращения** - редактирование словаря сокращений

## Требования

- Python 3.8+
- Node.js 16+
- npm или yarn

