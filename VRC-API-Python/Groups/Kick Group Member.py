import requests

url = "https://api.vrchat.cloud/api/1/groups/grp_00000000-0000-0000-0000-000000000000/members/string"

response = requests.request("DELETE", url, cookies = {
  "auth": ""
})

print(response.text)