const body = JSON.stringify({
  "code": "string"
})

fetch("https://api.vrchat.cloud/api/1/auth/twofactorauth/totp/pending/verify", {
  headers: {
    "cookie": "auth="
  },
  body
})