# Configuration
$email = "raghavkkapoor7seller@gmail.com"
$password = "enpovlfbcgeelwgx" # Replace with your 16-character APP PASSWORD (google settings)






# Connect to Gmail IMAP server over SSL (Port 993)
$client = New-Object System.Net.Sockets.TcpClient("imap.gmail.com", 993)
$stream = New-Object System.Net.Security.SslStream($client.GetStream(), $false)
$stream.AuthenticateAsClient("imap.gmail.com")

$writer = New-Object System.IO.StreamWriter($stream)
$reader = New-Object System.IO.StreamReader($stream)
$writer.AutoFlush = $true

function Send-IMAPCommand($tag, $command) {
    $writer.WriteLine("$tag $command")
    $output = @()
    while ($true) {
        $line = $reader.ReadLine()
        $output += $line
        if ($line -like "$tag OK*" -or $line -like "$tag NO*" -or $line -like "$tag BAD*") {
            break
        }
    }
    return $output
}

try {
    # Read server greeting
    $null = $reader.ReadLine()

    # 1. Authenticate
    $loginRes = Send-IMAPCommand "A1" "LOGIN $email $password"
    if ($loginRes[-1] -notlike "A1 OK*") {
        throw "Login failed. Check your email and App Password."
    }
    Write-Host "Successfully connected to Gmail IMAP!" -ForegroundColor Green

    # 2. Select the Inbox
    $null = Send-IMAPCommand "A2" "SELECT INBOX"

    # 3. Search specifically for unread Primary messages
    $searchRes = Send-IMAPCommand "A3" 'SEARCH X-GM-RAW "category:primary is:unread"'
    
    # Isolate strictly the data line starting with '* SEARCH'
    $searchLine = $searchRes | Where-Object { $_ -match '^\*\s+SEARCH' }
    $rawIds = $searchLine -replace '^\*\s+SEARCH\s*', ''

    # Filter out anything that isn't a pure number
    $emailIds = ($rawIds -split '\s+') | Where-Object { $_ -match '^\d+$' }

    if (-not $emailIds) {
        Write-Host "No unread messages found in Primary inbox." -ForegroundColor Yellow
    } else {
        # 4. Limit to the last 5 (newest) numeric IDs
        if ($emailIds.Count -gt 5) {
            $emailIds = $emailIds[-5..-1]
        }

        Write-Host "Found $($emailIds.Count) recent unread Primary email(s):" -ForegroundColor Cyan

        # 5. Fetch headers for the selected messages
        foreach ($id in $emailIds) {
            $fetchRes = Send-IMAPCommand "A4" "FETCH $id (BODY[HEADER.FIELDS (FROM SUBJECT DATE)])"
            Write-Host "`n--- Message ID: $id ---" -ForegroundColor DarkCyan
            
            $fetchRes | Where-Object { $_ -match "^(From|Subject|Date):" } | ForEach-Object {
                Write-Host $_
            }
        }
    }

    # 6. Logout
    $null = Send-IMAPCommand "A5" "LOGOUT"
}
catch {
    Write-Error "IMAP Error: $_"
}
finally {
    # Clean up connections
    $writer.Close()
    $reader.Close()
    $stream.Close()
    $client.Close()
}