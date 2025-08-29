fetch("https://api.vrchat.cloud/api/1/auth", {
  headers: {
    "cookie": "auth="
  }
})


=====

Authorization
auth<token>

Auth Token via Cookie

In: cookie

=====

Response Body
200
Returns wether a provided auth token is valid or not.
ok boolean
token string
Length 1 <= length


401
Error response due to missing auth cookie.
error? Response
