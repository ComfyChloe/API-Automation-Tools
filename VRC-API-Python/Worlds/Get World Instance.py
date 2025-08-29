import requests

url = "https://api.vrchat.cloud/api/1/worlds/string/string"

response = requests.request("GET", url, cookies = {
  "auth": ""
})

print(response.text)