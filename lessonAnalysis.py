import requests
import anthropic
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

directory_path = Path("./lesson_output")

client = anthropic.Anthropic()

url = "https://europe-west2-brilliantmuslim.cloudfunctions.net/mobile-api/course?course_id=c-001"

response = requests.get(url)
data = response.json()

output = ""

def deleteAllFiles(): 
    for element in client.beta.files.list():
        print(element.id)
        client.beta.files.delete(element.id)

deleteAllFiles();

for k in range(1, 2):
    output = ""
    title = data["lessons"][k]["title"]
    responseInitial = requests.get(data["lessons"][k]["lessonUrl"]).json() # the index here represents the surah
    if (data["lessons"][k]["lessonType"] == "collection"):
        for j in range(len(responseInitial["lessons"])):
            print(j)
            responseSecond = requests.get(responseInitial["lessons"][j]["lessonUrl"]).json() # the index here represents the ayah group
            responseThird = requests.get(responseSecond["story"]["url"]).json()
            responseQuiz = requests.get(responseSecond["quizzes"][0]["url"]).json()

            for i in range(2):
                for x in range(len(responseThird["pages"][i]["blocks"])):
                    output = output + responseThird["pages"][i]["blocks"][x]["text"] + "\n"

            with open(f"./lesson_output/{title} Part {j+1}.txt", "w", encoding="utf-8") as file:
                file.write(output)

            for i in range(len(responseQuiz["questions"])):
                print(responseQuiz["questions"][i]["title"])

                print(i)


                
                if responseQuiz["questions"][i]["answerType"] == "single":
                    with open(f"./lesson_output/{title} Part {j+1}.txt", "a", encoding="utf-8") as file:
                        file.write(f"{responseQuiz["questions"][i]["title"]} \n")

                    for k in range(len(responseQuiz["questions"][i]["choices"])):
                        with open(f"./lesson_output/{title} Part {j+1}.txt", "a", encoding="utf-8") as file:
                            file.write(f"{responseQuiz["questions"][i]["choices"][k]["text"]} - {responseQuiz["questions"][i]["choices"][k]["isCorrect"]} \n")

                    with open(f"./lesson_output/{title} Part {j+1}.txt", "a", encoding="utf-8") as file:
                        file.write(f"Explanation: {responseQuiz["questions"][i]["explanation"]} \n")

            output = ""

    else:
        responseSecond = requests.get(responseInitial["story"]["url"]).json()

        for k in range(len(responseSecond["pages"][1]["blocks"])):
            if "text" in responseSecond["pages"][1]["blocks"][k]:
                print(responseSecond["pages"][1]["blocks"][k])
                output = output + responseSecond["pages"][1]["blocks"][k]["text"] + "\n"

        with open(f"./lesson_output/{title}.txt", "w", encoding="utf-8") as file:
            file.write(output)

        for j in range(len(responseInitial["quizzes"])):
            responseThird = requests.get(responseInitial["quizzes"][j]["url"]).json()

            for i in range(len(responseThird["questions"])):
                print(responseThird["questions"][i]["title"])

                print(i)


                
                if responseThird["questions"][i]["answerType"] == "single":
                    with open(f"./lesson_output/{title}.txt", "a", encoding="utf-8") as file:
                        file.write(f"{responseThird["questions"][i]["title"]} \n")
                
                    for k in range(len(responseThird["questions"][i]["choices"])):
                        with open(f"./lesson_output/{title}.txt", "a", encoding="utf-8") as file:
                            file.write(f"{responseThird["questions"][i]["choices"][k]["text"]} - {responseThird["questions"][i]["choices"][k]["isCorrect"]} \n")

ids = []

for file_path in directory_path.iterdir():
    with file_path.open("rb") as file:
        uploaded = client.beta.files.upload(
            file=(file_path.name, file, "text/plain"),
        )
    
    ids.append({"id": uploaded.id, "title": file_path.name})
    
for obj in ids:
    response = client.beta.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "The attached document is a lesson on a specific surah of the Quran. The lesson is made for English speaking learners, and is part of an app that allows users to quickly learn about the Quran on the go. Give feedback about the background and facts of the lessons. Following the lesson are the quizzes associated with it. Give feedback on the answer option clarity, whether there are any mistakes in the answers or explanation, and whether the explanation is simple/clear or can be better."},
                    {
                        "type": "document",
                        "source": {
                            "type": "file",
                            "file_id": obj["id"],
                        },
                    },
                ],
            }
        ],
        betas=["files-api-2025-04-14"],
    )
    print(response)
    print(response.content[0].text)
    with open(f"./lesson_analysis/{obj["title"]}", "w", encoding="utf-8") as file:
        file.write(response.content[0].text)
    
deleteAllFiles();

print(client.beta.files.list())



# Go through one lesson/quiz for a surah at a time and provide a single feedback file in MARKdown format
# If the surah has multiple lessons name the feedback files with a similar naming pattern to the API (part 1, part 2)
# Look into access aqqal GPT
# look into testing multiple open source models against each other
# Look into openrouter for comparing LLMs
# Evaluation on the model feedback

# Phase two is to ask the model to improve the lesson based on the feedback it gave
# Seperate system prompt that gives a score for a lesson so we can compare the score before and after lesson improvement