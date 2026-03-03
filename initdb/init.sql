create type week_type as enum ('обе недели','числитель','знаменатель');
create type class_type as enum ('лекция', 'практика', 'лабораторная', 'консультация', 'экзамен', 'зачет', 'пересдача');
create type override_action as enum ('cancel','replace','add');

-- Создание таблицы semester
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

-- Создание таблицы department
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

-- Создание таблицы direction
CREATE TABLE direction (
    id BIGSERIAL PRIMARY KEY,
    code TEXT,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы student_group
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


-- Создание таблицы room
CREATE TABLE room (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    building VARCHAR(16),
    capacity INT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- Создание таблицы teacher
CREATE TABLE teacher (
    id BIGSERIAL PRIMARY KEY,
    fio TEXT NOT NULL,
    is_external BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы subject
CREATE TABLE subject (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы timeslot
CREATE TABLE timeslot (
    id BIGSERIAL PRIMARY KEY,
    pair_number INT NOT NULL,
    building VARCHAR(16),
    time_start TIME NOT NULL,
    time_end TIME NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT timeslot_time_check 
        CHECK (time_start < time_end)
);

-- Создание таблицы schedule_pattern_item
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
        ON DELETE RESTRICT
);

-- Создание таблицы schedule_override
CREATE TABLE schedule_override (
    id BIGSERIAL PRIMARY KEY,

    weekday INT NOT NULL CHECK (weekday BETWEEN 1 AND 7),

    teacher_id BIGINT,
    subject_id BIGINT,

    week_type week_type NOT NULL DEFAULT 'обе недели',
    class_type class_type NOT NULL,

    room_id BIGINT,

    group_id BIGINT,
    subgroup_count INT,
    subgroup_no INT,

    semester_id BIGINT NOT NULL,

    duration_pairs NUMERIC(3,1) CHECK (duration_pairs BETWEEN 1 AND 8),

    is_remote BOOLEAN NOT NULL DEFAULT FALSE,

    timeslot_no INT NOT NULL,
    time_start_custom TIME,
    time_end_custom TIME,

    source_pattern_item_id BIGINT,

    note TEXT,

    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT schedule_override_time_custom_check
        CHECK (time_start_custom IS NULL OR time_end_custom IS NULL OR time_start_custom < time_end_custom),

    CONSTRAINT fk_schedule_override_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES teacher(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    CONSTRAINT fk_schedule_override_subject
        FOREIGN KEY (subject_id)
        REFERENCES subject(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    CONSTRAINT fk_schedule_override_room
        FOREIGN KEY (room_id)
        REFERENCES room(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    CONSTRAINT fk_schedule_override_group
        FOREIGN KEY (group_id)
        REFERENCES student_group(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    CONSTRAINT fk_schedule_override_semester
        FOREIGN KEY (semester_id)
        REFERENCES semester(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

INSERT INTO timeslot (pair_number, building, time_start, time_end)
VALUES
-- Корпус А
(1, 'А', '08:30', '09:50'),
(2, 'А', '10:00', '11:20'),
(3, 'А', '11:30', '12:50'),
(4, 'А', '13:20', '14:40'),
(5, 'А', '14:50', '16:10'),
(6, 'А', '16:20', '17:40'),
(7, 'А', '18:00', '19:20'),
(8, 'А', '19:30', '20:50'),
(9, 'А', '21:00', '22:20'),

-- Корпус Г
(1, 'Г', '08:30', '09:50'),
(2, 'Г', '10:00', '11:20'),
(3, 'Г', '11:30', '12:50'),
(4, 'Г', '13:20', '14:40'),
(5, 'Г', '14:50', '16:10'),
(6, 'Г', '16:20', '17:40'),
(7, 'Г', '18:00', '19:20'),
(8, 'Г', '19:30', '20:50'),
(9, 'Г', '21:00', '22:20'),

-- Корпус К
(1, 'К', '08:30', '09:50'),
(2, 'К', '10:00', '11:20'),
(3, 'К', '11:30', '12:50'),
(4, 'К', '13:20', '14:40'),
(5, 'К', '14:50', '16:10'),
(6, 'К', '16:20', '17:40'),
(7, 'К', '18:00', '19:20'),
(8, 'К', '19:30', '20:50'),
(9, 'К', '21:00', '22:20'),

-- Корпус У
(1, 'У', '08:30', '09:50'),
(2, 'У', '10:00', '11:20'),
(3, 'У', '11:30', '12:50'),
(4, 'У', '13:20', '14:40'),
(5, 'У', '14:50', '16:10'),
(6, 'У', '16:20', '17:40'),
(7, 'У', '18:00', '19:20'),
(8, 'У', '19:30', '20:50'),
(9, 'У', '21:00', '22:20');

-- Корпус МК
INSERT INTO timeslot (pair_number, building, time_start, time_end)
VALUES
(1, 'МК', '09:00', '10:20'),
(2, 'МК', '10:30', '11:50'),
(3, 'МК', '12:00', '13:20'),
(4, 'МК', '13:30', '14:50'),
(5, 'МК', '15:00', '16:20'),
(6, 'МК', '16:30', '17:50'),
(7, 'МК', '18:00', '19:20'),
(8, 'МК', '19:30', '20:50');


-- делай только если реально нет дублей в данных!
ALTER TABLE teacher   ADD CONSTRAINT ux_teacher_fio UNIQUE (fio);
ALTER TABLE subject   ADD CONSTRAINT ux_subject_name UNIQUE (name);
ALTER TABLE institute ADD CONSTRAINT ux_institute_name UNIQUE (name);
ALTER TABLE room      ADD CONSTRAINT ux_room_name UNIQUE (name);
ALTER TABLE direction ADD CONSTRAINT ux_direction_code UNIQUE (code);