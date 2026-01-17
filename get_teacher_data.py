import requests as rq
from bs4 import BeautifulSoup
import json
mass = []
for i in range(0, 1000):
    print(i)
    objectData = {}
    objectData["fio"] = ""
    objectData["post_name"] = ""
    objectData["post_struct"] = ""
    objectData["all_staj"] = ""
    objectData["staj_spec"] = ""
    objectData["phone"] = ""
    objectData["predmet"] = ""
    url = "https://www.surgu.ru/ru/peoples/" + str(i)
    response = rq.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    data = soup.find('div', {'class': "white-popup-block staff_details"})
    if data:
        if data.find('h2'):
            objectData["fio"] = data.find('h2').text
        if data.find('span',{'class': 'staff_post-name'}):
            objectData["post_name"] = data.find('span',{'class': 'staff_post-name'}).text
        if data.find('span',{'class': 'staff_post-struct'}):
            objectData["post_struct"] = data.find('span',{'class': 'staff_post-struct'}).text
        if data.find_all('li',{'class': 'person_list_item post_text'}):
            person_list = data.find_all('li',{'class': 'person_list_item post_text'})
            for q in person_list:
                if "Общий стаж" in q.text:
                    objectData["all_staj"] = q.text.replace("\n", "")
                elif "Стаж работы" in q.text:
                    objectData["staj_spec"] = q.text.replace("\n", "")
                elif "Телефон" in q.text:
                    objectData["phone"] = q.text.replace("\n", "")
        if data.find('ol',{'class': 'person_post_list person_list'}):
            all_predmet = data.find('ol',{'class': 'person_post_list person_list'})
            if all_predmet:
                all_predmet = all_predmet.find_all('li',{'class': 'staff_post person_list_item'})
                predmet = ""
                for q in all_predmet:
                    predmet = predmet + q.text + "|"
                objectData["predmet"] = predmet
        mass.append(objectData)
with open("teacher_all.json", "w") as json_file:
    json.dump(mass, json_file)

