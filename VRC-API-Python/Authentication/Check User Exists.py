import requests

url = "https://api.vrchat.cloud/api/1/auth/exists?email=string&displayName=string&username=string&excludeUserId=string"

response = requests.request("GET", url)

print(response.text)