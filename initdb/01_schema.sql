-- Создание таблиц в БД surgu_timetable (POSTGRES_DB)
-- Выполняется при первой инициализации контейнера

CREATE TABLE IF NOT EXISTS intermediate_timetable (
    id               INTEGER PRIMARY KEY,
    cleaned_id       INTEGER,
    teacher_id       INTEGER,
    day_of_week      VARCHAR(50),
    pair_number      INTEGER,
    subject_name     TEXT,
    discipline_original TEXT,
    lecture_type     VARCHAR(50),
    audience         VARCHAR(50),
    group_name       VARCHAR(50),
    week_type        VARCHAR(50),
    subgroup         INTEGER,
    institute        TEXT,
    course           VARCHAR(10),
    direction        TEXT,
    department       TEXT,
    is_external      BOOLEAN,
    is_remote        BOOLEAN,
    num_subgroups    INTEGER,
    fio              TEXT,
    week_error       BOOLEAN,
    audience_error   BOOLEAN
);

CREATE TABLE IF NOT EXISTS schedule (
    id            INTEGER,
    day_of_week   VARCHAR(50),
    pair_number   INTEGER,
    subject_name  TEXT,
    lecture_type  VARCHAR(50),
    audience      VARCHAR(50),
    group_name    VARCHAR(50),
    week_type     VARCHAR(50),
    subgroup      INTEGER,
    institute     TEXT,
    course        VARCHAR(10),
    direction     TEXT,
    department    TEXT,
    is_external   BOOLEAN,
    is_remote     BOOLEAN,
    num_subgroups INTEGER,
    fio           TEXT
);

CREATE TABLE IF NOT EXISTS timetable_aspi (
    id                   INTEGER,
    day_of_week          VARCHAR(50),
    pair_number          TEXT,
    subject_name         TEXT,
    discipline_original  TEXT,
    audience             VARCHAR(255),
    group_name           VARCHAR(100),
    week_type            VARCHAR(50),
    fio                  TEXT,
    course               VARCHAR(20),
    scientific_specialty TEXT
);

CREATE TABLE IF NOT EXISTS timetable_cleaned (
    id            INTEGER,
    day_of_week   VARCHAR(50),
    pair_number   INTEGER,
    subject_name  TEXT,
    lecture_type  VARCHAR(50),
    audience      VARCHAR(50),
    fio           TEXT,
    teacher       TEXT,
    group_name    VARCHAR(50),
    week_type     VARCHAR(50),
    subgroup      INTEGER,
    institute     TEXT,
    course        VARCHAR(10),
    direction     TEXT,
    department    TEXT,
    is_external   BOOLEAN,
    is_remote     BOOLEAN,
    num_subgroups INTEGER,
    created_at    TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS timetable_teacher (
    id            INTEGER,
    fio           TEXT,
    pair_number   INTEGER,
    day_of_week   VARCHAR(50),
    group_name    VARCHAR(50),
    audience      VARCHAR(50),
    department    TEXT,
    week_type     VARCHAR(50),
    subgroup      INTEGER,
    num_subgroups INTEGER,
    is_external   BOOLEAN,
    is_remote     BOOLEAN,
    subject_name  TEXT,
    created_at    TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS user_prefs (
    chat_id     VARCHAR(64),
    entity_type VARCHAR(20),
    entity_value TEXT,
    updated_at  TIMESTAMPTZ
);
