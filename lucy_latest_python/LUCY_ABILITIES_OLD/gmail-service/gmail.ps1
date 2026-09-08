param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("WhoAmI","Send","Search","Latest")]
    [string]$Action,

    [string]$To = "",
    [string]$Subject = "",
    [string]$Body = "",
    [string[]]$Attachment = @(),

    [string]$Query = "",
    [int]$MaxResults = 10,

    [switch]$UnreadOnly,
    [switch]$InboxOnly
)

$ErrorActionPreference = "Stop"

$Root = "C:\Users\ragha\Downloads\LUCY\LucyPython"
$CredFile = Join-Path $Root "cred.json"
$OAuthHelper = Join-Path $Root "LUCY_ABILITIES\gmail-service\oauth-required.py"
$Api = "https://gmail.googleapis.com/gmail/v1"

function Save-Credential {
    param($Credential)

    $Credential |
        ConvertTo-Json -Depth 10 |
        Set-Content -LiteralPath $CredFile -Encoding UTF8
}

function Start-FreshOAuth {
    param([string]$Reason)

    Write-Output "GMAIL_AUTH_REQUIRED=True"
    Write-Output "AUTH_REASON=$Reason"

    if (Test-Path -LiteralPath $OAuthHelper) {
        Start-Process `
            -FilePath "python.exe" `
            -ArgumentList "`"$OAuthHelper`"" `
            -WorkingDirectory $Root

        Write-Output "OAUTH_STARTED=True"
    }
    else {
        Write-Output "OAUTH_STARTED=False"
    }

    Write-Output "RETRY_AFTER_AUTH=True"
}

function Refresh-GmailToken {
    param($Credential)

    if (-not $Credential.refresh_token) {
        return $false
    }

    $tokenUri = if ($Credential.token_uri) {
        [string]$Credential.token_uri
    }
    else {
        "https://oauth2.googleapis.com/token"
    }

    $responseFile = Join-Path $env:TEMP (
        "lucy_gmail_refresh_" + [guid]::NewGuid().ToString("N") + ".json"
    )

    $args = @(
        "--silent",
        "--show-error",
        "--connect-timeout","3",
        "--max-time","8",
        "--request","POST",
        "--output",$responseFile,
        "--write-out","%{http_code}",
        "--data-urlencode",("client_id=" + $Credential.client_id),
        "--data-urlencode",("client_secret=" + $Credential.client_secret),
        "--data-urlencode",("refresh_token=" + $Credential.refresh_token),
        "--data-urlencode","grant_type=refresh_token",
        $tokenUri
    )

    try {
        $http = & curl.exe @args
        $exit = $LASTEXITCODE

        if ($exit -ne 0 -or $http -ne "200") {
            return $false
        }

        $result = Get-Content -LiteralPath $responseFile -Raw -Encoding UTF8 |
            ConvertFrom-Json

        if (-not $result.access_token) {
            return $false
        }

        $Credential.token = $result.access_token

        if ($result.scope) {
            $Credential.scopes = @(
                ([string]$result.scope).Split(
                    " ",
                    [System.StringSplitOptions]::RemoveEmptyEntries
                )
            )
        }

        $Credential.expiry = (Get-Date).ToUniversalTime().
            AddSeconds([int]$result.expires_in).
            ToString("yyyy-MM-ddTHH:mm:ss.ffffffZ")

        Save-Credential $Credential

        Write-Output "GMAIL_TOKEN_REFRESHED=True"
        return $true
    }
    finally {
        Remove-Item $responseFile -Force -ErrorAction SilentlyContinue
    }
}

function Get-GmailCredential {
    if (-not (Test-Path -LiteralPath $CredFile)) {
        Start-FreshOAuth "CREDENTIAL_FILE_MISSING"
        return $null
    }

    try {
        $credential = Get-Content -LiteralPath $CredFile -Raw -Encoding UTF8 |
            ConvertFrom-Json
    }
    catch {
        Start-FreshOAuth "CREDENTIAL_FILE_INVALID"
        return $null
    }

    if (-not $credential.token) {
        if (-not (Refresh-GmailToken $credential)) {
            Start-FreshOAuth "NO_ACCESS_TOKEN"
            return $null
        }
    }

    if ($credential.expiry) {
        try {
            $expiry = [datetimeoffset]::Parse([string]$credential.expiry)

            if ($expiry -le [datetimeoffset]::Now.AddMinutes(1)) {
                if (-not (Refresh-GmailToken $credential)) {
                    Start-FreshOAuth "TOKEN_REFRESH_FAILED"
                    return $null
                }

                $credential = Get-Content -LiteralPath $CredFile -Raw -Encoding UTF8 |
                    ConvertFrom-Json
            }
        }
        catch {
            if (-not (Refresh-GmailToken $credential)) {
                Start-FreshOAuth "TOKEN_EXPIRY_INVALID"
                return $null
            }

            $credential = Get-Content -LiteralPath $CredFile -Raw -Encoding UTF8 |
                ConvertFrom-Json
        }
    }

    return $credential
}

function Invoke-GmailApi {
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet("GET","POST")]
        [string]$Method,

        [Parameter(Mandatory=$true)]
        [string]$Url,

        [object]$JsonBody = $null
    )

    $credential = Get-GmailCredential

    if (-not $credential) {
        return $null
    }

    for ($attempt = 1; $attempt -le 2; $attempt++) {

        $responseFile = Join-Path $env:TEMP (
            "lucy_gmail_response_" +
            [guid]::NewGuid().ToString("N") +
            ".json"
        )

        $bodyFile = $null

        $args = @(
            "--silent",
            "--show-error",
            "--connect-timeout","3",
            "--max-time","8",
            "--http1.1",
            "--request",$Method,
            "--header",("Authorization: Bearer " + $credential.token),
            "--header","Accept: application/json"
        )

        if ($null -ne $JsonBody) {
            $bodyFile = Join-Path $env:TEMP (
                "lucy_gmail_request_" +
                [guid]::NewGuid().ToString("N") +
                ".json"
            )

            $JsonBody |
                ConvertTo-Json -Depth 15 -Compress |
                Set-Content -LiteralPath $bodyFile -Encoding UTF8

            $args += @(
                "--header","Content-Type: application/json",
                "--data-binary",("@$bodyFile")
            )
        }

        $args += @(
            "--output",$responseFile,
            "--write-out","%{http_code}",
            $Url
        )

        try {
            $http = & curl.exe @args
            $curlExit = $LASTEXITCODE

            if ($curlExit -ne 0) {
                throw "curl.exe failed with exit code $curlExit"
            }

            $responseText = if (Test-Path -LiteralPath $responseFile) {
                Get-Content -LiteralPath $responseFile -Raw -Encoding UTF8
            }
            else {
                ""
            }

            if ($http -eq "401" -and $attempt -eq 1) {
                if (Refresh-GmailToken $credential) {
                    $credential = Get-Content -LiteralPath $CredFile -Raw -Encoding UTF8 |
                        ConvertFrom-Json
                    continue
                }

                Start-FreshOAuth "HTTP_401"
                return $null
            }

            if ([int]$http -lt 200 -or [int]$http -ge 300) {
                Write-Output "GMAIL_API_ERROR=True"
                Write-Output "HTTP_STATUS=$http"

                if ($responseText) {
                    Write-Output "RESPONSE=$responseText"
                }

                throw "Gmail API HTTP $http"
            }

            if ([string]::IsNullOrWhiteSpace($responseText)) {
                return [pscustomobject]@{}
            }

            return ($responseText | ConvertFrom-Json)
        }
        finally {
            Remove-Item $responseFile -Force -ErrorAction SilentlyContinue

            if ($bodyFile) {
                Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue
            }
        }
    }

    return $null
}

function Get-GmailProfile {
    return Invoke-GmailApi `
        -Method GET `
        -Url "$Api/users/me/profile"
}

if ($Action -eq "WhoAmI") {
    $profile = Get-GmailProfile

    if ($profile) {
        Write-Output "GMAIL_AUTHENTICATED=True"
        Write-Output "EMAIL=$($profile.emailAddress)"
        Write-Output "TRANSPORT=CURL"
    }

    Write-Output "GMAIL_CALL_COMPLETE=True"
    exit 0
}

if ($Action -eq "Send") {
    if ([string]::IsNullOrWhiteSpace($To)) {
        throw "Send requires -To"
    }

    $profile = Get-GmailProfile

    if (-not $profile) {
        Write-Output "GMAIL_CALL_COMPLETE=True"
        exit 0
    }

    $boundary = "LUCY_" + [guid]::NewGuid().ToString("N")

    $mime = New-Object System.Text.StringBuilder

    [void]$mime.Append("From: $($profile.emailAddress)`r`n")
    [void]$mime.Append("To: $To`r`n")
    [void]$mime.Append("Subject: $Subject`r`n")
    [void]$mime.Append("MIME-Version: 1.0`r`n")

    if (@($Attachment).Count -eq 0) {
        [void]$mime.Append("Content-Type: text/plain; charset=utf-8`r`n")
        [void]$mime.Append("`r`n")
        [void]$mime.Append($Body)
    }
    else {
        [void]$mime.Append(
            "Content-Type: multipart/mixed; boundary=`"$boundary`"`r`n`r`n"
        )

        [void]$mime.Append("--$boundary`r`n")
        [void]$mime.Append("Content-Type: text/plain; charset=utf-8`r`n`r`n")
        [void]$mime.Append($Body + "`r`n")

        foreach ($file in @($Attachment)) {
            if (-not (Test-Path -LiteralPath $file)) {
                throw "Attachment missing: $file"
            }

            $name = [System.IO.Path]::GetFileName($file)
            $bytes = [System.IO.File]::ReadAllBytes($file)
            $b64 = [Convert]::ToBase64String(
                $bytes,
                [Base64FormattingOptions]::InsertLineBreaks
            )

            [void]$mime.Append("--$boundary`r`n")
            [void]$mime.Append("Content-Type: application/octet-stream; name=`"$name`"`r`n")
            [void]$mime.Append("Content-Disposition: attachment; filename=`"$name`"`r`n")
            [void]$mime.Append("Content-Transfer-Encoding: base64`r`n`r`n")
            [void]$mime.Append($b64 + "`r`n")
        }

        [void]$mime.Append("--$boundary--`r`n")
    }

    $rawBytes = [Text.Encoding]::UTF8.GetBytes($mime.ToString())

    $raw = [Convert]::ToBase64String($rawBytes).
        TrimEnd("=").
        Replace("+","-").
        Replace("/","_")

    $result = Invoke-GmailApi `
        -Method POST `
        -Url "$Api/users/me/messages/send" `
        -JsonBody @{ raw = $raw }

    if ($result -and $result.id) {
        Write-Output "GMAIL_SEND_VERIFIED=True"
        Write-Output "MESSAGE_ID=$($result.id)"
        Write-Output "TO=$To"
        Write-Output "ATTACHMENT_COUNT=$(@($Attachment).Count)"
    }

    Write-Output "GMAIL_CALL_COMPLETE=True"
    exit 0
}

if ($Action -eq "Latest") {
    $parts = @()

    if ($UnreadOnly) { $parts += "is:unread" }
    if ($InboxOnly) { $parts += "in:inbox" }

    $Query = $parts -join " "
}

if ($Action -eq "Search" -or $Action -eq "Latest") {
    $MaxResults = [Math]::Max(
        1,
        [Math]::Min($MaxResults,100)
    )

    $url = "$Api/users/me/messages?maxResults=$MaxResults"

    if ($Query) {
        $url += "&q=" + [uri]::EscapeDataString($Query)
    }

    $listing = Invoke-GmailApi -Method GET -Url $url

    if (-not $listing) {
        Write-Output "GMAIL_CALL_COMPLETE=True"
        exit 0
    }

    $items = @($listing.messages)

    Write-Output "RESULT_COUNT=$($items.Count)"
    Write-Output "GMAIL_QUERY=$Query"

    foreach ($entry in $items) {
        $msg = Invoke-GmailApi `
            -Method GET `
            -Url "$Api/users/me/messages/$($entry.id)?format=metadata"

        if (-not $msg) { continue }

        $headers = @{}

        foreach ($h in @($msg.payload.headers)) {
            $headers[$h.name] = $h.value
        }

        [pscustomobject]@{
            id = $msg.id
            thread_id = $msg.threadId
            from = $headers["From"]
            to = $headers["To"]
            cc = $headers["Cc"]
            subject = $headers["Subject"]
            date = $headers["Date"]
            labels = @($msg.labelIds)
        } | ConvertTo-Json -Compress -Depth 6
    }

    Write-Output "GMAIL_CALL_COMPLETE=True"
    exit 0
}
