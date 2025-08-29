import requests

url = "https://api.vrchat.cloud/api/1/user/string/friendRequest"

response = requests.request("POST", url, cookies = {
  "auth": ""
})

print(response.text)