#!/bin/bash
# Скрипт для установки зависимостей в venv

cd "$(dirname "$0")"

if [ -d "venv" ]; then
    echo "Активируем venv и устанавливаем зависимости..."
    source venv/bin/activate
    pip install requests beautifulsoup4 lxml pdfplumber Flask Flask-Cors
    echo "✅ Зависимости установлены!"
else
    echo "❌ venv не найден. Создайте его:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install requests beautifulsoup4 lxml pdfplumber Flask Flask-Cors"
fi

