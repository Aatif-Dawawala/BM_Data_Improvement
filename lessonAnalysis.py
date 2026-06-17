import requests
import anthropic
from pathlib import Path
import os
from dotenv import load_dotenv
import json

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

for k in range(0, 1):
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
                
                if responseThird["questions"][i]["answerType"] == "single":

                    if responseInitial["quizzes"][j]["title"] == "Vocabulary" and "audioData" in responseThird["questions"][i]:
                        with open(f"./lesson_output/{title}.txt", "a", encoding="utf-8") as file:
                            file.write(f"{responseThird["questions"][i]["title"]} - {responseThird["questions"][i]["audioData"]["text"]}\n")

                    else: 
                        with open(f"./lesson_output/{title}.txt", "a", encoding="utf-8") as file:
                            file.write(f"{responseThird["questions"][i]["title"]} \n")
                
                    for k in range(len(responseThird["questions"][i]["choices"])):
                        with open(f"./lesson_output/{title}.txt", "a", encoding="utf-8") as file:
                            file.write(f"{responseThird["questions"][i]["choices"][k]["text"]} - {responseThird["questions"][i]["choices"][k]["isCorrect"]} \n")

                    with open(f"./lesson_output/{title}.txt", "a", encoding="utf-8") as file:
                        file.write(f"Explanation: {responseThird["questions"][i]["explanation"]} \n")
            
                

ids = []

for file_path in directory_path.iterdir():
    with file_path.open("rb") as file:
        uploaded = client.beta.files.upload(
            file=(file_path.name, file, "text/plain"),
        )
    
    ids.append({"id": uploaded.id, "title": file_path.stem})
    
for obj in ids:
    response = client.beta.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "The attached document is a lesson on a specific surah of the Quran. The lesson is made for English speaking learners, and is part of an app that allows users to quickly learn about the Quran on the go. Give feedback in markdown format about the background and facts of the lessons. Following the lesson are the quizzes associated with it. Give feedback on the answer option clarity, whether there are any mistakes in the answers or explanation, and whether the explanation is simple/clear or can be better. Don't mention what is done well, just mention improvement points."},
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

    with open(f"./lesson_analysis/{obj["title"]}.md", "w", encoding="utf-8") as file:
        file.write(response.content[0].text)

# headers = {"Authorization": f"Bearer {os.getenv("OPENROUTER_API_KEY")}"}

# for file_path in directory_path.iterdir():
#     with file_path.open("rb") as file:
#         uploaded = requests.post("https://openrouter.ai/api/v1/files", files=file, headers=headers)

#     ids.append({"id": uploaded.id, "title": file_path.stem})

# for obj in ids:
#     response = requests.post(
#         url="https://openrouter.ai/api/v1/chat/completions",
#         headers={
#             "Authorization": f"Bearer {os.getenv("OPENROUTER_API_KEY")}"
#         },
#         data=json.dumps({
#             "model": "~openai/gpt-latest",
#             "messages": [
#                 {
#                     "role": "user",
#                     "content": ""
#                 }
#             ]
#         })
#     )
    
deleteAllFiles();

print(client.beta.files.list())



