import requests
import anthropic
from pathlib import Path
import os
from dotenv import load_dotenv

def deleteAllFiles(): 
    for element in client.beta.files.list():
        print(element.id)
        client.beta.files.delete(element.id)

load_dotenv()

directory_path = Path("./lesson_output")

client = anthropic.Anthropic()

url = "https://europe-west2-brilliantmuslim.cloudfunctions.net/mobile-api/course?course_id=c-001"

response = requests.get(url)
data = response.json()

output = ""

deleteAllFiles()

for k in range(0, 1):
    output = ""
    title = data["lessons"][k]["title"]
    responseInitial = requests.get(data["lessons"][k]["lessonUrl"]).json() 

    if (data["lessons"][k]["lessonType"] == "collection"):
        for j in range(len(responseInitial["lessons"])):
            responseSecond = requests.get(responseInitial["lessons"][j]["lessonUrl"]).json() # the index here represents the ayah group
            responseThird = requests.get(responseSecond["quizzes"][0]["url"]).json()

            print(j)

            for i in range(len(responseThird["questions"])):
                print(responseThird["questions"][i]["title"])

                print(i)

                with open(f"./lesson_output/{title} Part {j + 1}.txt", "w", encoding="utf-8") as file:
                    file.write(f"{responseThird["questions"][i]["title"]} \n")
                
                if responseThird["questions"][i]["answerType"] == "single":
                    for k in range(len(responseThird["questions"][i]["choices"])):
                        with open(f"./lesson_output/{title} Part {j + 1}.txt", "a", encoding="utf-8") as file:
                            file.write(f"{responseThird["questions"][i]["choices"][k]["text"]} - {responseThird["questions"][i]["choices"][k]["isCorrect"]} \n")

    if (data["lessons"][k]["lessonType"] == "single"):
        for j in range(len(responseInitial["quizzes"])):
            responseThird = requests.get(responseInitial["quizzes"][j]["url"]).json()

            for i in range(len(responseThird["questions"])):
                    print(responseThird["questions"][i]["title"])

                    print(i)

                    with open(f"./lesson_output/{title} Part {j + 1}.txt", "w", encoding="utf-8") as file:
                        file.write(f"{responseThird["questions"][i]["title"]} \n")
                    
                    if responseThird["questions"][i]["answerType"] == "single":
                        for k in range(len(responseThird["questions"][i]["choices"])):
                            with open(f"./lesson_output/{title} Part {j + 1}.txt", "a", encoding="utf-8") as file:
                                file.write(f"{responseThird["questions"][i]["choices"][k]["text"]} - {responseThird["questions"][i]["choices"][k]["isCorrect"]} \n")
