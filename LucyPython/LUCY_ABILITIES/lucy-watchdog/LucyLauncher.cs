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
        int X,
        int Y,
        int cx,
        int cy,
        uint flags
    );

    static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);

    const uint SWP_NOSIZE = 0x0001;
    const uint SWP_NOMOVE = 0x0002;
    const uint SWP_NOACTIVATE = 0x0010;

    static int Main()
    {
        string root =
            @"C:\Users\ragha\Downloads\LUCY\LucyPython";

        string watchdog = Path.Combine(
            root,
            "LUCY_ABILITIES",
            "lucy-watchdog",
            "watchdog.py"
        );

        if (!File.Exists(watchdog))
        {
            Console.Error.WriteLine(
                "Lucy watchdog missing: " + watchdog
            );

            Console.ReadKey();
            return 1;
        }

        Console.Title = "LUCY";

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
                    SWP_NOSIZE |
                    SWP_NOMOVE |
                    SWP_NOACTIVATE
                );

                break;
            }

            Thread.Sleep(100);
        }

        ProcessStartInfo psi = new ProcessStartInfo();

        psi.FileName = "python.exe";
        psi.Arguments = "-u \"" + watchdog + "\"";
        psi.WorkingDirectory = root;

        // Important:
        // watchdog/main.py remain attached to this console,
        // so Lucy's normal input() still works.
        psi.UseShellExecute = false;

        using (Process process = Process.Start(psi))
        {
            if (process == null)
                return 1;

            process.WaitForExit();
            return process.ExitCode;
        }
    }
}
