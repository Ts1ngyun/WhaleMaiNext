using System;
using WhaleLauncher;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length != 2 || args[0] != "--voice-reply-job") return 2;
        return AutoVoiceWorker.Run(AppContext.BaseDirectory, args[1]).GetAwaiter().GetResult();
    }
}
