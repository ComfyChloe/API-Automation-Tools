fetch("https://api.vrchat.cloud/api/1/auth/exists?email=string&displayName=string&username=string&excludeUserId=string")

=======

Query Parameters
email?string

Filter by email.
displayName?string

Filter by displayName.
username?string

Filter by Username.
excludeUserId?string

Exclude by UserID.

=======

Response Body

200
Returns a response if a user exists or not.

userExists boolean
Status if a user exist with that username or userId.
Default false

nameOk? boolean
Is the username valid?
Default false

statuscode
400
Error response when missing at least 1 of the required parameters.
error?Response
