param(
    [Parameter(Mandatory = $true)]
    [string]$Email,

    [Parameter(Mandatory = $true)]
    [string]$Password
)

$cdpHost = "127.0.0.1"
$cdpPort = 9223
$loginUrl = "https://id.bcit.ca/my.policy"
$ws = $null
$cts = $null
$script:cdpId = 0

function Send-CDP {
    param([string]$Method, [hashtable]$Params = @{})

    $script:cdpId++
    $id = $script:cdpId
    $message = @{ id = $id; method = $Method; params = $Params } |
        ConvertTo-Json -Depth 30 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($message)
    $script:ws.SendAsync(
        [ArraySegment[byte]]::new($bytes),
        [Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        $script:cts.Token
    ).GetAwaiter().GetResult() | Out-Null

    while ($true) {
        $buffer = New-Object byte[] 65536
        $memory = New-Object IO.MemoryStream
        do {
            $receive = $script:ws.ReceiveAsync(
                [ArraySegment[byte]]::new($buffer),
                $script:cts.Token
            ).GetAwaiter().GetResult()
            if ($receive.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) {
                throw "Chrome closed the CDP WebSocket connection."
            }
            if ($receive.Count -gt 0) { $memory.Write($buffer, 0, $receive.Count) }
        } while (-not $receive.EndOfMessage)

        $json = [Text.Encoding]::UTF8.GetString($memory.ToArray())
        $memory.Dispose()
        try { $response = $json | ConvertFrom-Json -ErrorAction Stop } catch { continue }
        if ($response.id -ne $id) { continue }
        if ($response.error) { throw "CDP error $($response.error.code): $($response.error.message)" }
        return $response
    }
}

function Invoke-BcitEvaluate {
    param(
        [string]$Expression,
        [bool]$AwaitPromise = $true,
        [bool]$AllowNavigation = $false
    )

    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        try {
            return Send-CDP "Runtime.evaluate" @{
                expression = $Expression
                returnByValue = $true
                awaitPromise = $AwaitPromise
            }
        }
        catch {
            $navigationError = $_.Exception.Message -match "Execution context was destroyed|Inspected target navigated or closed|WebSocket.*(closed|disposed)"
            if ($_.Exception.Message -notmatch "Cannot find default execution context|Execution context was destroyed|Inspected target navigated or closed|WebSocket.*(closed|disposed)") {
                throw
            }
            Connect-BcitPage
            if ($AllowNavigation -and $navigationError) {
                return @{ result = @{ result = @{ value = @{ success = $true } } } }
            }
            Start-Sleep -Milliseconds 250
        }
    }

    throw "BCIT page JavaScript context did not become available."
}

function Invoke-BcitStep {
    param([string]$StepName, [string]$Script)

    Write-Host $StepName
    $result = Invoke-BcitEvaluate $Script $true $true
    if ($result.result.exceptionDetails) {
        $details = $result.result.exceptionDetails
        if ($details.exception.description) { throw $details.exception.description }
        throw $details.text
    }

    $value = $result.result.result.value
    if (-not $value.success) { throw $value.error }
}

function Get-BcitUrl {
    $result = Invoke-BcitEvaluate "location.href" $false
    return [string]$result.result.result.value
}

function Stop-IfBcitDashboard {
    $url = Get-BcitUrl
    if ($url -match '^https://my\.bcit\.ca/') {
        Write-Host "BCIT Dashboard detected. Login complete."
        exit
    }

    $dashboardCheck = @'
(() => [...document.querySelectorAll("*")]
    .filter(el => el !== document.body && getComputedStyle(el).display !== "none" &&
        el.getBoundingClientRect().width > 0 &&
        (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().includes("Dashboard"))
    .sort((a, b) => (a.innerText || a.textContent || "").length - (b.innerText || b.textContent || "").length)
    .length > 0)()
'@
    $result = Invoke-BcitEvaluate $dashboardCheck $false
    if ($result.result.result.value -eq $true) {
        Write-Host "BCIT Dashboard detected. Login complete."
        exit
    }
}

function Connect-BcitPage {
    if ($script:ws) { try { $script:ws.Dispose() } catch {} }
    if ($script:cts) { try { $script:cts.Dispose() } catch {} }

    $pages = Invoke-RestMethod "http://${cdpHost}:${cdpPort}/json/list" -ErrorAction Stop
    $page = $pages |
        Where-Object { $_.type -eq "page" -and ($_.url -match "bcit|login|auth|sso|microsoftonline") } |
        Select-Object -First 1
    if (-not $page) {
        $page = $pages | Where-Object { $_.type -eq "page" } | Select-Object -First 1
    }

    $wsEndpoint = [string]$page.PSObject.Properties["webSocketDebuggerUrl"].Value
    if ([string]::IsNullOrWhiteSpace($wsEndpoint)) { throw "No browser page found on CDP port $cdpPort." }

    $script:ws = [Net.WebSockets.ClientWebSocket]::new()
    $script:cts = [Threading.CancellationTokenSource]::new()
    $script:ws.ConnectAsync([Uri]::new($wsEndpoint), $script:cts.Token).GetAwaiter().GetResult() | Out-Null
    Send-CDP "Page.enable" | Out-Null
    Send-CDP "Runtime.enable" | Out-Null
}

function Close-CDP {
    try {
        if ($script:ws -and $script:ws.State -eq [Net.WebSockets.WebSocketState]::Open) {
            $script:ws.CloseAsync(
                [Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                "Done",
                [Threading.CancellationToken]::None
            ).GetAwaiter().GetResult() | Out-Null
        }
    } catch {}
    try { if ($script:ws) { $script:ws.Dispose() } } catch {}
    try { if ($script:cts) { $script:cts.Dispose() } } catch {}
}

try {
    Connect-BcitPage
    Send-CDP "Page.navigate" @{ url = $loginUrl } | Out-Null

    Start-Sleep -Seconds 2

    $emailJson = $Email | ConvertTo-Json -Compress
    $emailStep = @'
(async () => {
    const value = __VALUE__;
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    const input = () => document.querySelector("input[aria-label='BCIT email'], input[type='email'], input[name='username']");
    const button = name => [...document.querySelectorAll("button, input[type='submit'], input[type='button'], [role='button']")].find(el =>
        visible(el) && ((el.innerText || el.value || el.getAttribute("aria-label") || "").trim() === name));
    for (let i = 0; i < 120 && !visible(input()); i++) await sleep(250);
    const field = input();
    if (!visible(field)) return { success: false, error: "BCIT email field not found." };
    field.focus();
    field.value = value;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
    let next = button("Next");
    for (let i = 0; i < 120 && !next; i++) { await sleep(250); next = button("Next"); }
    if (!next) return { success: false, error: "BCIT Next button not found." };
    next.click();
    return { success: true };
})()
'@.Replace('__VALUE__', $emailJson)

    Stop-IfBcitDashboard
    Invoke-BcitStep "Entering BCIT email..." $emailStep
    Start-Sleep -Seconds 2

    $secondEmailStep = @'
(async () => {
    const value = __VALUE__;
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    const field = () => document.querySelector("input[placeholder*='user@bcit.ca'], input[placeholder*='my.bcit'], input[type='email']");
    const next = () => [...document.querySelectorAll("button, input[type='submit'], input[type='button'], [role='button']")].find(el => visible(el) && (el.innerText || el.value || el.getAttribute("aria-label") || "").trim() === "Next");
    for (let i = 0; i < 120 && !visible(field()); i++) await sleep(250);
    const emailField = field();
    if (!visible(emailField)) return { success: false, error: "Second BCIT email field not found." };
    emailField.focus();
    emailField.value = value;
    emailField.dispatchEvent(new Event("input", { bubbles: true }));
    emailField.dispatchEvent(new Event("change", { bubbles: true }));
    let nextButton = next();
    for (let i = 0; i < 120 && !nextButton; i++) { await sleep(250); nextButton = next(); }
    if (!nextButton) return { success: false, error: "Second BCIT Next button not found." };
    nextButton.click();
    return { success: true };
})()
'@.Replace('__VALUE__', $emailJson)

    Stop-IfBcitDashboard
    Invoke-BcitStep "Confirming BCIT email..." $secondEmailStep
    Start-Sleep -Seconds 2

    $passwordJson = $Password | ConvertTo-Json -Compress
    $passwordStep = @'
(async () => {
    const value = __VALUE__;
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    const field = () => document.querySelector("input[type='password'], input[aria-label*='Enter the password']");
    const button = () => [...document.querySelectorAll("button, input[type='submit'], input[type='button'], [role='button']")].find(el => visible(el) && (el.innerText || el.value || el.getAttribute("aria-label") || "").trim() === "Sign in");
    for (let i = 0; i < 120 && !visible(field()); i++) await sleep(250);
    const passwordField = field();
    if (!visible(passwordField)) return { success: false, error: "BCIT password field not found." };
    passwordField.focus();
    passwordField.value = value;
    passwordField.dispatchEvent(new Event("input", { bubbles: true }));
    passwordField.dispatchEvent(new Event("change", { bubbles: true }));
    let signIn = button();
    for (let i = 0; i < 120 && !signIn; i++) { await sleep(250); signIn = button(); }
    if (!signIn) return { success: false, error: "BCIT Sign in button not found." };
    signIn.click();
    return { success: true };
})()
'@.Replace('__VALUE__', $passwordJson)

    Stop-IfBcitDashboard
    Invoke-BcitStep "Signing in to BCIT..." $passwordStep
    Start-Sleep -Seconds 2

    $authCode = Read-Host "Enter Google Authenticator code"
    if ([string]::IsNullOrWhiteSpace($authCode)) { throw "No authenticator code entered." }
    $authJson = $authCode.Trim() | ConvertTo-Json -Compress
    $authStep = @'
(async () => {
    const value = __VALUE__;
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    const field = () => document.querySelector("input[aria-label*='Enter code'], input[autocomplete='one-time-code'], input[inputmode='numeric']");
    const button = () => [...document.querySelectorAll("button, input[type='submit'], input[type='button'], [role='button']")].find(el => visible(el) && (el.innerText || el.value || el.getAttribute("aria-label") || "").trim() === "Verify");
    for (let i = 0; i < 120 && !visible(field()); i++) await sleep(250);
    const codeField = field();
    if (!visible(codeField)) return { success: false, error: "Authenticator code field not found." };
    codeField.focus();
    codeField.value = value;
    codeField.dispatchEvent(new Event("input", { bubbles: true }));
    codeField.dispatchEvent(new Event("change", { bubbles: true }));
    let verify = button();
    for (let i = 0; i < 120 && !verify; i++) { await sleep(250); verify = button(); }
    if (!verify) return { success: false, error: "BCIT Verify button not found." };
    verify.click();
    return { success: true };
})()
'@.Replace('__VALUE__', $authJson)

    Stop-IfBcitDashboard
    Invoke-BcitStep "Verifying authenticator code..." $authStep
    Start-Sleep -Seconds 2

    if ((Get-BcitUrl) -match '^https://my\.bcit\.ca/') {
        Write-Host "BCIT authentication complete."
        exit
    }

    $rememberStep = @'
(async () => {
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    const labelText = el => (el.innerText || el.textContent || el.value || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
    const yes = () => [...document.querySelectorAll("button, input[type='submit'], input[type='button'], [role='button']")].find(el => visible(el) && labelText(el).toLowerCase() === "yes");
    for (let i = 0; i < 40; i++) {
        if (location.href.startsWith("https://my.bcit.ca/")) return { success: true };
        if (yes()) break;
        await sleep(250);
    }
    if (location.href.startsWith("https://my.bcit.ca/")) return { success: true };
    const checkboxLabel = [...document.querySelectorAll("label, span, div")].find(el => visible(el) && labelText(el).toLowerCase() === "don't show this again");
    const checkbox = checkboxLabel?.querySelector("input[type='checkbox']") || document.querySelector("input[type='checkbox']");
    if (checkbox && !checkbox.checked) checkbox.click();
    const yesButton = yes();
    if (!yesButton) {
        if (location.href.startsWith("https://my.bcit.ca/")) return { success: true };
        return { success: false, error: "BCIT Yes button not found." };
    }
    yesButton.click();
    return { success: true };
})()
'@

    Stop-IfBcitDashboard
    Invoke-BcitStep "Completing BCIT verification..." $rememberStep
    Start-Sleep -Seconds 3

    $dashboardStep = @'
(async () => {
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    const text = el => (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    for (let i = 0; i < 120; i++) {
        const dashboard = [...document.querySelectorAll("*")]
            .filter(el => el !== document.body && visible(el) && text(el).includes("Dashboard"))
            .sort((a, b) => text(a).length - text(b).length)[0];
        if (dashboard) { dashboard.click(); return { success: true }; }
        await sleep(250);
    }
    return { success: false, error: "BCIT Dashboard link not found." };
})()
'@

    Stop-IfBcitDashboard
    Invoke-BcitStep "Opening BCIT Dashboard..." $dashboardStep
    Write-Host "BCIT login sequence complete."
}
catch {
    Write-Host "`nERROR:"
    Write-Host $_.Exception.Message
}
finally {
    Close-CDP
}
