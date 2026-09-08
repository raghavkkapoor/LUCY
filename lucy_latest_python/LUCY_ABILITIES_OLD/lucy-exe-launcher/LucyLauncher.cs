using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
class LucyLauncher
{
    [DllImport("user32.dll")]
    static extern bool SetWindowPos(
        IntPtr hWnd,
        IntPtr hWndInsertAfter,
        int X, int Y, int cx, int cy,
        uint flags
    );
    static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
    const uint SWP_NOSIZE = 0x0001;
    const uint SWP_NOMOVE = 0x0002;
    const uint SWP_NOACTIVATE = 0x0010;
    static int Main(string[] args)
    {
        string root = @"C:\Users\ragha\Downloads\LUCY\LucyPython";
        string main = Path.Combine(root, "main.py");
        if (!File.Exists(main))
        {
            Console.Error.WriteLine("main.py not found: " + main);
            Console.ReadKey();
            return 1;
        }
        Console.Title = "LUCY";
        // Make this console window topmost after Windows creates it.
        for (int i = 0; i < 30; i++)
        {
            Process current = Process.GetCurrentProcess();
            current.Refresh();
            if (current.MainWindowHandle != IntPtr.Zero)
            {
                SetWindowPos(
                    current.MainWindowHandle,
                    HWND_TOPMOST,
                    0, 0, 0, 0,
                    SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
                );
                break;
            }
            Thread.Sleep(100);
        }
        var psi = new ProcessStartInfo
        {
            FileName = "python.exe",
            Arguments = "\"" + main + "\"",
            WorkingDirectory = root,
            UseShellExecute = false
        };
        try
        {
            using (Process python = Process.Start(psi))
            {
                if (python == null)
                    throw new Exception("python.exe failed to start.");
                python.WaitForExit();
                return python.ExitCode;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Lucy failed to launch: " + ex.Message);
            Console.ReadKey();
            return 1;
        }
    }
}
