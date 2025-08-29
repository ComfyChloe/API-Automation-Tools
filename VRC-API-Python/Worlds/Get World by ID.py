import requests

url = "https://api.vrchat.cloud/api/1/worlds/string"

response = requests.request("GET", url)

print(response.text)