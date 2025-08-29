fetch("https://api.vrchat.cloud/api/1/auth/user", {
  headers: {
    "Authorization": "Basic Og=="
  }
})


=====


Authorization
AuthorizationBasic <token>

Auth token via Header

In: header


Response Body
200
Response Body

OK
acceptedTOSVersioninteger
Range0 <= value
acceptedPrivacyVersion? integer
Range0 <= value
accountDeletionDate? string
Format date
accountDeletionLog? array<AccountDeletionLog>
activeFriends? array<UserID>
ageVerificationStatus AgeVerificationStatus

verified is obsolete.

User who have verified and are 18+ can switch to plus18 status.
Value in "hidden" | "verified" | "18+"
ageVerified AgeVerified

true if, user is age verified (not 18+).
allowAvatarCopying boolean
authToken? string

The auth token for NEWLY REGISTERED ACCOUNTS ONLY (/auth/register)
badges?array<Badge>
bio string
bioLinks array<string>
contentFilters? array<Tag>

These tags begin with content_ and control content gating
currentAvatar AvatarID
currentAvatarImageUrl CurrentAvatarImageUrl

When profilePicOverride is not empty, use it instead.
currentAvatarThumbnailImageUrlCurrentAvatarThumbnailImageUrl

When profilePicOverride is not empty, use it instead.
currentAvatarTags array<Tag>
date_joined string
Format date
developerType DeveloperType

"none" User is a normal user "trusted" Unknown "internal" Is a VRChat Developer "moderator" Is a VRChat Moderator

Staff can hide their developerType at will.
Default "none"
Value in "none" | "trusted" | "internal" | "moderator"
displayName string
emailVerified boolean
fallbackAvatar? AvatarID Deprecated
friendGroupNames array<string> Deprecated

Always empty array.
friendKey string
friends array<UserID>
hasBirthday boolean
hideContentFilterSettings? boolean
userLanguage? string
userLanguageCode? string
hasEmail boolean
hasLoggedInFromClient boolean
hasPendingEmail boolean
homeLocationWorldID

WorldID be "offline" on User profiles if you are not friends with that user.
idUserID

A users unique ID, usually in the form of usr_c1644b5b-3ca4-45b4-97c6-a2a0de70d469. Legacy players can have old IDs in the form of 8JoV9XEdpo. The ID can never be changed.
isAdult boolean
isBoopingEnabled? boolean
Default true
isFriend boolean
Default false
last_activity? string
Formatdate-time
last_login string
Formatdate-time
last_mobile string
Formatdate-time
last_platform Platform

This can be standalone windows or android, but can also pretty much be any random Unity verison such as 2019.2.4-801-Release or 2019.2.2-772-Release or even unknown platform.
obfuscatedEmail string
obfuscatedPendingEmail string
oculusId string
googleId? string
googleDetails? object

Empty Object
picoId? string
viveId? string
offlineFriends? array<UserID>
onlineFriends? array<UserID>
pastDisplayNames array<PastDisplayName>
presence? CurrentUserPresence
platform_history? array<object>
profilePicOverride string
profilePicOverrideThumbnail string
pronouns string
queuedInstance? string
receiveMobileInvitations? boolean
stateUserState

    "online" User is online in VRChat
    "active" User is online, but not in VRChat
    "offline" User is offline

Always offline when returned through getCurrentUser (/auth/user).
Default "offline"
Value in "offline" | "active" | "online"
statusUserStatus

Defines the User's current status, for example "ask me", "join me" or "offline. This status is a combined indicator of their online activity and privacy preference.
Default "offline"
Value in "active" | "join me" | "ask me" | "busy" | "offline"
statusDescription string
statusFirstTime boolean
statusHistory array<string>
steamDetails object

Empty Object
steamId string
tags array<Tag>
twoFactorAuthEnabled boolean
twoFactorAuthEnabledDate? string
Formatdate-time
unsubscribe boolean
updated_at? string
Formatdate-time
userIconstring

401

Error response due to missing auth cookie.
error?Response
message? string
Length1 <= length
status_code integer
Range100 <= value