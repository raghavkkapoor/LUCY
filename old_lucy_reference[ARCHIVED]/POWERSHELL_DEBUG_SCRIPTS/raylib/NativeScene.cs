using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace RaylibCommandHost {
    public sealed class Scene {
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate void FrameDelegate(double time, float delta, int frame, int width, int height, int firstFrame);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern IntPtr LoadLibraryExW(string path, IntPtr file, uint flags);
        [DllImport("kernel32.dll", CharSet=CharSet.Ansi, ExactSpelling=true, SetLastError=true)]
        private static extern IntPtr GetProcAddress(IntPtr module, string name);
        // Keep modules alive until process exit: native callbacks can retain code pointers.
        private static readonly Dictionary<string, Scene> scenes = new Dictionary<string, Scene>(StringComparer.OrdinalIgnoreCase);
        private readonly IntPtr library;
        private readonly FrameDelegate draw;
        private Scene(string path) {
            library = LoadLibraryExW(path, IntPtr.Zero, 8);
            if (library == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "Cannot load C scene: " + path);
            IntPtr address = GetProcAddress(library, "RaylibCommandFrame");
            if (address == IntPtr.Zero) throw new InvalidOperationException("C scene does not export RaylibCommandFrame.");
            draw = (FrameDelegate)Marshal.GetDelegateForFunctionPointer(address, typeof(FrameDelegate));
        }
        public static Scene Get(string path) {
            Scene result;
            if (!scenes.TryGetValue(path, out result)) { result = new Scene(path); scenes.Add(path, result); }
            return result;
        }
        public void Draw(double time, float delta, int frame, int width, int height, int firstFrame) {
            draw(time, delta, frame, width, height, firstFrame);
        }
    }
}
