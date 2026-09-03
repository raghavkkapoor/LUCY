using System.Net.WebSockets;
using System;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Text.Json;

namespace TransparentRectangleWpf;

internal static class GeminiClient
{
    private const string CdpBaseUrl = "http://127.0.0.1:9223";
    private const string GeminiUrl = "https://gemini.google.com/";

    public static async Task<string> SendAsync(string request)
    {
        using var http = new HttpClient();
        using var tabResponse = await http.PutAsync(
            $"{CdpBaseUrl}/json/new?{Uri.EscapeDataString(GeminiUrl)}", null);
        tabResponse.EnsureSuccessStatusCode();
        using var tab = JsonDocument.Parse(await tabResponse.Content.ReadAsStringAsync());
        var socketUrl = tab.RootElement.GetProperty("webSocketDebuggerUrl").GetString()
            ?? throw new InvalidOperationException("Gemini tab did not provide a WebSocket URL.");

        using var socket = new ClientWebSocket();
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMinutes(3));
        await socket.ConnectAsync(new Uri(socketUrl), cancellation.Token);
        var cdp = new CdpConnection(socket, cancellation.Token);

        await cdp.SendAsync("Page.enable", new { });
        await cdp.SendAsync("Page.navigate", new { url = GeminiUrl });
        await WaitForRuntimeAsync(cdp, cancellation.Token);

        var requestJson = JsonSerializer.Serialize(request);
        var javascript = $@"
(async () => {{
    const request = {requestJson};
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const visible = el => el && getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().width > 0;
    const responseText = () => {{
        const turns = [...document.querySelectorAll('message-content, model-response, div.model-response, .response-container')].filter(visible);
        const texts = turns.map(turn => (turn.innerText || '').trim()).filter(text => text && text !== request.trim());
        return texts.length ? texts[texts.length - 1] : '';
    }};
    try {{
        let composer = document.querySelector('rich-textarea .ql-editor');
        for (let i = 0; i < 120 && !visible(composer); i++) {{
            await sleep(250);
            composer = document.querySelector('rich-textarea .ql-editor');
        }}
        if (!visible(composer)) return {{ success: false, error: 'Gemini composer not found.' }};
        composer.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('insertText', false, request);
        composer.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: request }}));
        composer.dispatchEvent(new Event('change', {{ bubbles: true }}));

        let button = document.querySelector('button.send-button, button[aria-label*=""Send""], button[aria-label*=""Submit""]');
        for (let i = 0; i < 120 && !visible(button); i++) {{
            await sleep(250);
            button = document.querySelector('button.send-button, button[aria-label*=""Send""], button[aria-label*=""Submit""]');
        }}
        if (!visible(button)) return {{ success: false, error: 'Gemini send button not found.' }};
        const before = responseText();
        let sawGeneration = false;
        button.click();
        for (let i = 0; i < 240; i++) {{
            const stop = document.querySelector('button[aria-label*=""Stop response""]');
            const text = responseText();
            if (stop) sawGeneration = true;
            if (!stop && text && (sawGeneration || text !== before)) return {{ success: true, text }};
            await sleep(100);
        }}
        const text = responseText();
        return text && (sawGeneration || text !== before)
            ? {{ success: true, text }}
            : {{ success: false, error: 'Gemini response timed out.' }};
    }} catch (err) {{
        return {{ success: false, error: err?.message || String(err) }};
    }}
}})()";

        var result = await cdp.EvaluateAsync(javascript, true);
        if (result.TryGetProperty("success", out var success) && success.GetBoolean())
            return result.GetProperty("text").GetString() ?? string.Empty;

        throw new InvalidOperationException(
            result.TryGetProperty("error", out var error)
                ? error.GetString()
                : "Gemini returned an invalid response.");
    }

    private static async Task WaitForRuntimeAsync(CdpConnection cdp, CancellationToken token)
    {
        for (var i = 0; i < 80; i++)
        {
            try
            {
                var state = await cdp.EvaluateAsync("document.readyState");
                if (state.GetString() == "complete") return;
            }
            catch (InvalidOperationException ex) when (
                ex.Message.Contains("execution context", StringComparison.OrdinalIgnoreCase)) { }
            await Task.Delay(250, token);
        }
        throw new TimeoutException("Gemini page load timed out.");
    }

    private sealed class CdpConnection
    {
        private readonly ClientWebSocket _socket;
        private readonly CancellationToken _token;
        private int _nextId;

        public CdpConnection(ClientWebSocket socket, CancellationToken token)
        {
            _socket = socket;
            _token = token;
        }

        public async Task<JsonElement> SendAsync(string method, object parameters)
        {
            var id = Interlocked.Increment(ref _nextId);
            var message = JsonSerializer.SerializeToUtf8Bytes(new { id, method, @params = parameters });
            await _socket.SendAsync(message, WebSocketMessageType.Text, true, _token);

            while (true)
            {
                using var memory = new MemoryStream();
                WebSocketReceiveResult received;
                do
                {
                    var buffer = new byte[65536];
                    received = await _socket.ReceiveAsync(buffer, _token);
                    if (received.MessageType == WebSocketMessageType.Close)
                        throw new InvalidOperationException("Chrome closed the CDP connection.");
                    await memory.WriteAsync(buffer.AsMemory(0, received.Count), _token);
                } while (!received.EndOfMessage);

                using var document = JsonDocument.Parse(memory.ToArray());
                var root = document.RootElement.Clone();
                if (!root.TryGetProperty("id", out var responseId) || responseId.GetInt32() != id)
                    continue;
                if (root.TryGetProperty("error", out var error))
                    throw new InvalidOperationException(error.GetProperty("message").GetString());
                return root;
            }
        }

        public async Task<JsonElement> EvaluateAsync(string expression, bool awaitPromise = false)
        {
            var response = await SendAsync("Runtime.evaluate",
                new { expression, returnByValue = true, awaitPromise });
            if (response.GetProperty("result").TryGetProperty("exceptionDetails", out var details))
                throw new InvalidOperationException(details.GetProperty("text").GetString());
            return response.GetProperty("result").GetProperty("result").GetProperty("value").Clone();
        }
    }
}
