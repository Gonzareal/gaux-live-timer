// DAW falso para las pruebas reales en Windows: una ventana titulada como la del DAW, que se
// pone al frente y se cierra sola después de N segundos.
using System;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Windows.Forms;

class FakeDaw {
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);

    static void Front(Form f) {
        IntPtr fg = GetForegroundWindow();
        uint a = GetWindowThreadProcessId(fg, IntPtr.Zero), b = GetCurrentThreadId();
        if (a != b) AttachThreadInput(a, b, true);
        ShowWindow(f.Handle, 9);
        BringWindowToTop(f.Handle);
        SetForegroundWindow(f.Handle);
        f.Activate();
        if (a != b) AttachThreadInput(a, b, false);
    }

    [STAThread]
    static void Main(string[] args) {
        var f = new Form();
        f.Text = args.Length > 0 ? args[0] : "Untitled";
        f.Width = 1000; f.Height = 640;
        f.StartPosition = FormStartPosition.CenterScreen;
        f.Shown += (s, e) => { f.TopMost = true; Front(f); f.TopMost = false; };
        var t = new Timer();
        double secs = args.Length > 1 ? double.Parse(args[1], CultureInfo.InvariantCulture) : 120;
        t.Interval = (int)(secs * 1000);
        t.Tick += (s, e) => Application.Exit();
        t.Start();
        Application.Run(f);
    }
}
