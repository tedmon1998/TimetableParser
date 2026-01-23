const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');
const XLSX = require('xlsx');
const { Pool } = require('pg');

const url = 'https://www.surgu.ru/ucheba/raspisanie/zanyatost-prepodavateley';
// Создаем папки, если их нет
if (!fs.existsSync('input')) {
    fs.mkdirSync('input');
}
if (!fs.existsSync('output')) {
    fs.mkdirSync('output');
}
const path = `input/downloaded_file.xlsx`;


function arrayValidator(arr) {
    arr = arr.slice(0, 15)
    for (let i = arr.length; i < 15; i++) {
        arr[i] = null
    }
    return arr
}

function formatFullName(fullName) {
    if(fullName) {
        fullName = fullName.trim()
        var regex = /^([А-ЯЁ][а-яё]+)\s([А-ЯЁ])\.?\s?([А-ЯЁ])\.?$/;
        
        // Если ФИО соответствует шаблону, возвращаем его, иначе форматируем
        var match = fullName.match(regex);
        if (match) {
            // Извлекаем компоненты ФИО
            var lastName = match[1];
            var firstNameInitial = match[2];
            var middleNameInitial = match[3];
            
            // Форматируем ФИО
            var formattedFullName = lastName + " " + firstNameInitial + "." + middleNameInitial + ".";
            return formattedFullName;
        }
    }
    return fullName;
}




function updateDB() {
    console.log('Начинаем процесс обновления БД')

    const pool = new Pool({
        user: 'edro',
        host: '5.53.17.69',
        database: 'service_tg',
        password: '293e745b89f1',
        port: 50002,
    });
    // const pool = new Pool({
    //     user: 'edro',
    //     host: '5.53.17.69',
    //     database: 'service_tg',
    //     password: 'Pg123!',
    //     port: 50003,
    // });

    async function insertTeacher(short_name, department) {
        const resDepartment = await pool.query(`SELECT * FROM department WHERE id = $1`, [department])
        const departmentName = resDepartment.rows[0].name
        const resTeacherData = await pool.query(`INSERT INTO teacher_data (short_name, department) VALUES ($1, $2) RETURNING *`, [short_name, departmentName])
        teacherData = resTeacherData.rows[0]
        console.log(`Добавлен новый преподаватель ${short_name} из кафедры ${department} = ${departmentName}`)
        return teacherData.id
    }

    async function processExcelFile() {
        console.log('считываем excel')
        const workbook = XLSX.readFile(path);
        const sheetName = workbook.SheetNames[0];
        const sheet = workbook.Sheets[sheetName];
        // console.log(`sheet ${JSON.stringify(sheet)}`);
        // Получаем данные в виде массива массивов
        const data = XLSX.utils.sheet_to_json(sheet, {header:1}); 
        console.log(data.length)
        console.log('начинаем процесс заполнения БД новыми данными')
        const query = `INSERT INTO timetable (teacher, department, pair, monday, audience_mon, tuesday, audience_tues, wednesday, audience_wednes, thursday, audience_thurs, friday, audience_fri, saturday, audience_satur)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)`;
        for (let i = 1; i < data.length; i++) {
            console.log(`${i} < ${data.length}`)
            const row = arrayValidator(data[i]);
            // Значения из Excel соответствуют столбцам в БД
            console.log(JSON.stringify(row))
            const fio = formatFullName(row[0])
            if(fio !== "вакансия" && fio) {
                const teacher_data = await pool.query(`SELECT id, short_name FROM teacher_data WHERE short_name = $1`, [fio])
                console.log(`teacher_data ${JSON.stringify(teacher_data.rows[0])}`)
                if(teacher_data.rows[0]) {
                    row[0] = teacher_data.rows[0].id
                } else {
                    row[0] = await insertTeacher(formatFullName(row[0]), row[1])
                }
                const values = row;
                const res = await pool.query(query, values);
                console.log(`Строка добавлена: ${res.rowCount}`);
            }
        }
    }

    pool.query('DELETE FROM timetable', (err, res) => {
        if (err) {
            console.error(err);
        } else {
            console.log('Таблица очищена');
            // После очистки таблицы обрабатываем Excel файл
            processExcelFile();
        }
    });
}


axios.get(url).then(response => {
    const $ = cheerio.load(response.data);
    const downloadLink = $('a.file_block__link').attr('href');
    if (downloadLink) {
        const fullDownloadLink = `https://www.surgu.ru${downloadLink}`;
        console.log(`Найдена ссылка на скачивание: ${fullDownloadLink}`);
        axios({
            method: 'get',
            url: fullDownloadLink,
            responseType: 'stream'
        }).then(response => {
            const writer = fs.createWriteStream(path);
            response.data.pipe(writer);
            writer.on('finish', () => {
                console.log(`Файл скачан и сохранен как ${path}`);
                updateDB()
            })
             writer.on('error', (err) => {
                console.error('Произошла ошибка при записи файла:', err);
            });
        });
    }
});
