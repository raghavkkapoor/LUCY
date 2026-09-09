[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string]$Subject,

    [Parameter(Mandatory = $true)]
    [string]$Body,

    [Parameter(Mandatory = $false)]
    [string]$AttachmentPath,

    [Parameter(Mandatory = $false)]
    [string]$To = "raghavkkapoor7@gmail.com",

    [Parameter(Mandatory = $false)]
    [string]$From = "raghavkkapoor7@gmail.com",

    [Parameter(Mandatory = $false)]
    [string]$Password = "gvjohqpzvokxapuv",

    [Parameter(Mandatory = $false)]
    [string]$SmtpServer = "smtp.gmail.com",

    [Parameter(Mandatory = $false)]
    [int]$Port = 587
)

$tempZipPath = $null

try {
    # Convert plain string password to SecureString
    $secPassword = ConvertTo-SecureString $Password -AsPlainText -Force
    $credential = New-Object System.Management.Automation.PSCredential($From, $secPassword)

    $mailParams = @{
        From       = $From
        To         = $To
        Subject    = $Subject
        Body       = $Body
        SmtpServer = $SmtpServer
        Port       = $Port
        UseSsl     = $true
        Credential = $credential
        ErrorAction = "Stop"
    }

    # Handle attachment and compression logic
    if ($AttachmentPath) {
        if (-not (Test-Path -Path $AttachmentPath)) {
            throw "Attachment file not found at: $AttachmentPath"
        }

        $fileItem = Get-Item -Path $AttachmentPath
        $maxSizeBytes = 25 * 1MB

        if ($fileItem.Length -gt $maxSizeBytes) {
            Write-Host "File exceeds 25 MB ($([math]::Round($fileItem.Length / 1MB, 2)) MB). Compressing..." -ForegroundColor Yellow
            
            $tempZipPath = Join-Path -Path $env:TEMP -ChildPath "$($fileItem.BaseName)_compressed.zip"
            if (Test-Path $tempZipPath) { Remove-Item $tempZipPath -Force }

            Compress-Archive -Path $fileItem.FullName -DestinationPath $tempZipPath -CompressionLevel Optimal
            
            $zippedItem = Get-Item $tempZipPath
            Write-Host "Compressed size: $([math]::Round($zippedItem.Length / 1MB, 2)) MB" -ForegroundColor Cyan

            if ($zippedItem.Length -gt $maxSizeBytes) {
                Write-Warning "The compressed file still exceeds the 25 MB limit."
            }

            $mailParams["Attachments"] = $tempZipPath
        } else {
            $mailParams["Attachments"] = $fileItem.FullName
        }
    }

    Send-MailMessage @mailParams
    Write-Host "Email successfully sent to $To" -ForegroundColor Green
}
catch {
    Write-Error "Failed to send email: $_"
}
finally {
    # Clean up temporary zip file if created
    if ($tempZipPath -and (Test-Path $tempZipPath)) {
        Remove-Item $tempZipPath -Force
    }
}