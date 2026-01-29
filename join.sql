-- Объединение timetable_cleaned (спаршенное расписание) и timetable_teacher (занятость преподавателей)
-- по ключу: номер пары, аудитория, день недели, группа.
-- Флаг ошибки по полю "Неделя": если week_type не совпадает между таблицами.

SELECT
    c.id AS cleaned_id,
    t.id AS teacher_id,
    c.pair_number,
    c.day_of_week,
    c.group_name,
    c.audience,
    c.week_type       AS week_cleaned,
    t.week_type       AS week_teacher,
    -- Ключ ошибки по "Неделя": 0 = нет ошибки, 1 = есть ошибка
    CASE WHEN c.week_type IS NOT DISTINCT FROM t.week_type THEN 0 ELSE 1 END AS week_error_key,
    (c.week_type IS NOT DISTINCT FROM t.week_type) AS week_ok,
    CASE
        WHEN c.week_type IS NOT DISTINCT FROM t.week_type THEN 'нет ошибки'
        ELSE 'есть ошибка'
    END AS week_error_label,
    -- Данные из расписания
    c.subject_name     AS subject_cleaned,
    c.lecture_type,
    c.teacher         AS teacher_cleaned,
    c.fio             AS fio_cleaned,
    -- Данные из занятости
    t.fio             AS teacher_fio,
    t.subject_name     AS subject_teacher,
    t.department
FROM timetable_cleaned c
INNER JOIN timetable_teacher t
    ON c.pair_number IS NOT DISTINCT FROM t.pair_number
   AND NULLIF(TRIM(c.audience), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.audience), '')
   AND NULLIF(TRIM(c.day_of_week), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.day_of_week), '')
   AND NULLIF(TRIM(c.group_name), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.group_name), '')
ORDER BY c.day_of_week, c.pair_number, c.group_name;


-- Только строки с ошибкой по полю "Неделя" (week_type не совпадает):
/*
SELECT
    c.id AS cleaned_id,
    t.id AS teacher_id,
    c.pair_number,
    c.day_of_week,
    c.group_name,
    c.audience,
    c.week_type AS week_cleaned,
    t.week_type AS week_teacher,
    c.teacher   AS teacher_cleaned,
    t.fio       AS teacher_fio
FROM timetable_cleaned c
INNER JOIN timetable_teacher t
    ON c.pair_number IS NOT DISTINCT FROM t.pair_number
   AND NULLIF(TRIM(c.audience), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.audience), '')
   AND NULLIF(TRIM(c.day_of_week), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.day_of_week), '')
   AND NULLIF(TRIM(c.group_name), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.group_name), '')
WHERE (c.week_type IS NOT DISTINCT FROM t.week_type) IS FALSE
ORDER BY c.day_of_week, c.pair_number;
*/
