import requests

url = "https://api.vrchat.cloud/api/1/instances/string:string"

response = requests.request("GET", url, cookies = {
  "auth": ""
})

print(response.text)