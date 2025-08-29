import requests

url = "https://api.vrchat.cloud/api/1/time"

response = requests.request("GET", url)

print(response.text)