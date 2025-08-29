import requests

url = "https://api.vrchat.cloud/api/1/groups/grp_00000000-0000-0000-0000-000000000000/invites"
body = {
  "userId": "usr_c1644b5b-3ca4-45b4-97c6-a2a0de70d469"
}
response = requests.request("POST", url, json = body, headers = {
  "Content-Type": "application/json"
}, cookies = {
  "auth": ""
})

print(response.text)