fetch("https://api.vrchat.cloud/api/1/groups/grp_00000000-0000-0000-0000-000000000000?includeRoles=true", {
  headers: {
    "cookie": "auth="
  }
})



=====

Authorization
auth<token>

Auth Token via Cookie

In: cookie
Path Parameters
groupId string

Must be a valid group ID.
Query Parameters
includeRoles? boolean

Include roles for the Group object. Defaults to false.


Responce Body

200

Returns a single Group object.
ageVerificationSlotsAvailable? boolean
ageVerificationBetaCode? string
ageVerificationBetaSlots? number
badges? array<string>
id? GroupID
name? string
shortCode? GroupShortCode
discriminator? GroupDiscriminator
description? string
iconUrl? string
bannerUrl? string
privacy? GroupPrivacy
Default"default"
Value in"default" | "private"
ownerId? UserID

A users unique ID, usually in the form of usr_c1644b5b-3ca4-45b4-97c6-a2a0de70d469. Legacy players can have old IDs in the form of 8JoV9XEdpo. The ID can never be changed.
rules? string
links? array<string>
languages? array<string>
iconId? string
bannerId? string
memberCount? integer
memberCountSyncedAt? string
Formatdate-time
isVerified? boolean
Default false
joinState? GroupJoinState
Default "open"
Value in "closed" | "invite" | "request" | "open"
tags? array<Tag>
transferTargetId? UserID

A users unique ID, usually in the form of usr_c1644b5b-3ca4-45b4-97c6-a2a0de70d469. Legacy players can have old IDs in the form of 8JoV9XEdpo. The ID can never be changed.
galleries? array<GroupMember>
createdAt? string
Format date-time
updatedAt? string
Format date-time
lastPostCreatedAt? string
Format date-time
onlineMemberCount? integer
membershipStatus? string
Default "inactive"
Value in "inactive" | "member" | "requested" | "invited" | "banned" | "userblocked"
myMember? GroupMyMember
roles? array<GroupRole>

Only returned if ?includeRoles=true is specified.
