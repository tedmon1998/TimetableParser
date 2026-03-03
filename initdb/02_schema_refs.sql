-- Справочники и расписание: очистка и создание заново
-- Зависимости: сначала удаляем таблицы с FK, затем типы

DROP TABLE IF EXISTS schedule_override CASCADE;
DROP TABLE IF EXISTS schedule_pattern_item CASCADE;
DROP TABLE IF EXISTS timeslot CASCADE;
DROP TABLE IF EXISTS student_group CASCADE;
DROP TABLE IF EXISTS department CASCADE;
DROP TABLE IF EXISTS room CASCADE;
DROP TABLE IF EXISTS teacher CASCADE;
DROP TABLE IF EXISTS subject CASCADE;
DROP TABLE IF EXISTS direction CASCADE;
DROP TABLE IF EXISTS institute CASCADE;
DROP TABLE IF EXISTS semester CASCADE;

DROP TYPE IF EXISTS override_action;
DROP TYPE IF EXISTS class_type;
DROP TYPE IF EXISTS week_type;

-- Типы
CREATE TYPE week_type AS ENUM ('обе недели', 'числитель', 'знаменатель');
CREATE TYPE class_type AS ENUM ('лекция', 'практика', 'лабораторная');
CREATE TYPE override_action AS ENUM ('cancel', 'replace', 'add');

-- Семестр
CREATE TABLE semester (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    date_start DATE NOT NULL,
    date_end DATE NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT semester_date_check CHECK (date_start < date_end)
);

CREATE TABLE institute (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE department (
    id BIGSERIAL PRIMARY KEY,
    institute_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_department_institute
        FOREIGN KEY (institute_id)
        REFERENCES institute(id)
        ON DELETE CASCADE
);

CREATE TABLE direction (
    id BIGSERIAL PRIMARY KEY,
    code TEXT,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE student_group (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    institute_id BIGINT,
    direction_id BIGINT,
    department_id BIGINT,
    course INT NOT NULL CHECK (course BETWEEN 1 AND 6),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_group_institute
        FOREIGN KEY (institute_id)
        REFERENCES institute(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_group_direction
        FOREIGN KEY (direction_id)
        REFERENCES direction(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_group_department
        FOREIGN KEY (department_id)
        REFERENCES department(id)
        ON DELETE SET NULL
);

CREATE TABLE room (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    building VARCHAR(16),
    capacity INT,
    is_remote_room BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE teacher (
    id BIGSERIAL PRIMARY KEY,
    fio TEXT NOT NULL,
    is_external BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE subject (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE timeslot (
    id BIGSERIAL PRIMARY KEY,
    pair_number INT NOT NULL UNIQUE,
    building VARCHAR(16),
    time_start TIME NOT NULL,
    time_end TIME NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT timeslot_time_check
        CHECK (time_start < time_end)
);

CREATE TABLE schedule_pattern_item (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT,
    teacher_id BIGINT,
    action override_action NOT NULL,
    room_id BIGINT,
    subject_id BIGINT NOT NULL,
    class_type class_type NOT NULL,
    weekday INT NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    timeslot_no INT NOT NULL,
    time_start_custom TIME,
    time_end_custom TIME,
    week_type week_type NOT NULL DEFAULT 'обе недели',
    subgroup_no INT,
    duration_slots INT NOT NULL DEFAULT 1
        CHECK (duration_slots BETWEEN 1 AND 8),
    is_remote BOOLEAN NOT NULL DEFAULT FALSE,
    note TEXT,
    date_start DATE NOT NULL,
    date_end DATE NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT schedule_date_check
        CHECK (date_start <= date_end),
    CONSTRAINT schedule_time_custom_check
        CHECK (time_start_custom IS NULL OR time_end_custom IS NULL OR time_start_custom < time_end_custom),
    CONSTRAINT fk_schedule_group
        FOREIGN KEY (group_id)
        REFERENCES student_group(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_schedule_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES teacher(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_schedule_room
        FOREIGN KEY (room_id)
        REFERENCES room(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_schedule_subject
        FOREIGN KEY (subject_id)
        REFERENCES subject(id)
        ON DELETE RESTRICT,
);

CREATE TABLE schedule_override (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT,
    weekday INT CHECK (weekday BETWEEN 1 AND 7),
    week_type week_type,
    class_type class_type,
    timeslot_no INT,
    time_start_custom TIME,
    time_end_custom TIME,
    subgroup_count INT,
    subgroup_no INT,
    subject_id BIGINT,
    semester_id BIGINT,
    teacher_id BIGINT,
    room_id BIGINT,
    is_remote BOOLEAN,
    duration_pairs NUMERIC(3,1)
        CHECK (duration_pairs BETWEEN 1 AND 8),
    source_pattern_item_id BIGINT,
    note TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT schedule_override_time_custom_check
        CHECK (time_start_custom IS NULL OR time_end_custom IS NULL OR time_start_custom < time_end_custom),
    CONSTRAINT fk_override_group
        FOREIGN KEY (group_id)
        REFERENCES student_group(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_override_subject
        FOREIGN KEY (subject_id)
        REFERENCES subject(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_override_semester
        FOREIGN KEY (semester_id)
        REFERENCES semester(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_override_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES teacher(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_override_room
        FOREIGN KEY (room_id)
        REFERENCES room(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_override_source_pattern
        FOREIGN KEY (source_pattern_item_id)
        REFERENCES schedule_pattern_item(id)
        ON DELETE SET NULL
);
