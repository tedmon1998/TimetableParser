#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для запуска Flask приложения
"""
from app import app

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
