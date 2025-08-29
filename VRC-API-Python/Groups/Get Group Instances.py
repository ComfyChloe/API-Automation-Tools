import requests

url = "https://api.vrchat.cloud/api/1/groups/grp_00000000-0000-0000-0000-000000000000/instances"

response = requests.request("GET", url, cookies = {
  "auth": ""
})

print(response.text)