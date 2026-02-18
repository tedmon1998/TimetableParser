-- Объединение timetable_cleaned (спаршенное расписание) и timetable_teacher (занятость преподавателей)
-- по ключу: только день недели и аудитория (точное совпадение).
-- Из занятости берётся только ФИО преподавателя (t.fio).

SELECT
    c.id AS cleaned_id,
    t.id AS teacher_id,
    c.pair_number,
    c.day_of_week,
    c.group_name,
    c.audience,
    -- Данные из расписания
    c.subject_name     AS subject_cleaned,
    c.lecture_type,
    c.fio             AS fio_cleaned,
    -- Из занятости — только ФИО
    t.fio             AS teacher_fio
FROM timetable_cleaned c
INNER JOIN timetable_teacher t
    ON NULLIF(TRIM(c.day_of_week), '') IS NOT DISTINCT FROM NULLIF(TRIM(t.day_of_week), '')
   AND NULLIF(TRIM(COALESCE(c.audience, '')), '') IS NOT DISTINCT FROM NULLIF(TRIM(COALESCE(t.audience, '')), '')
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
