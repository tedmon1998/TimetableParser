# -*- coding: utf-8 -*-
"""Проверка парсинга числитель/знаменатель и аудиторий без Excel."""
import sys
sys.path.insert(0, '.')
from parse_timetable_excel import (
    is_audience,
    normalize_type_slash_for_weeks,
    build_combined_subject_and_audience,
    extract_audience,
    extract_audience_list,
)

def test_is_audience():
    assert is_audience('К511') is True
    assert is_audience('У708') is True
    assert is_audience('Управление') is False
    assert is_audience('Экономическая') is False
    assert is_audience('СОКБ') is True
    assert is_audience('К504') is True
    print('is_audience OK')

def test_normalize_slash():
    t = "Экономическое обоснование цифровых решений (лек)/(пр), К511"
    out = normalize_type_slash_for_weeks(t)
    assert '//' in out
    assert '(лек)' in out and '(пр)' in out
    assert 'К511' in out
    print('normalize_type_slash_for_weeks OK')

def test_build_combined():
    # Две части с А/Б: числитель К511, знаменатель К503
    raw = "Управление затратами (лек), К511/К503 // Управление затратами (пр), К511/К503"
    sn, aud = build_combined_subject_and_audience(raw)
    assert sn is not None
    assert 'Управление затратами (лек), К511' in sn
    assert 'Управление затратами (пр), К503' in sn
    assert aud == 'К511//К503'
    print('build_combined (К511/К503) OK')

    # Вторая часть только аудитория: "Часть1 // К511" -> "Часть1, К511"
    raw2 = "Управление затратами (лек) // К511"
    sn2, aud2 = build_combined_subject_and_audience(raw2)
    assert sn2 == "Управление затратами (лек), К511"
    assert aud2 == "К511"
    print('build_combined (// К511) OK')

def test_extract_audience():
    # Не должно быть "Управление" как аудитория
    t1 = "Управление затратами (лек), К511//"
    a1 = extract_audience(t1)
    assert 'Управление' not in a1
    assert 'К511' in a1
    print('extract_audience (no Управление) OK')

def test_audience_list():
    assert extract_audience_list("Дисц (лек), К511/К503") == ['К511', 'К503']
    assert extract_audience_list("Управление затратами (лек)") == []
    print('extract_audience_list OK')

if __name__ == '__main__':
    test_is_audience()
    test_normalize_slash()
    test_build_combined()
    test_extract_audience()
    test_audience_list()
    print('All OK')
