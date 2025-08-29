import requests

url = "https://api.vrchat.cloud/api/1/users/string/instances/groups"

response = requests.request("GET", url, cookies = {
  "auth": ""
})

print(response.text)