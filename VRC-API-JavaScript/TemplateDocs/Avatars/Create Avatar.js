const body = JSON.stringify({
  "name": "string",
  "imageUrl": "string"
})

fetch("https://api.vrchat.cloud/api/1/avatars", {
  headers: {
    "cookie": "auth="
  },
  body
})