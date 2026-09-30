using System.Diagnostics;

namespace Synapse.Generator.Tests.Helpers;

/// <summary>
/// Runs a git command for tests that need a repository of their own.
/// </summary>
/// <remarks>
/// Identity and dates are passed explicitly on every commit: a test must not depend on the
/// machine's git config, and a recorded date is the only way a history-dependent assertion
/// can mean the same thing tomorrow.
/// </remarks>
internal static class GitCommand
{
    /// <summary>Fixed instant for every commit these helpers make.</summary>
    public const string FixedDate = "2026-08-04T12:00:00+00:00";

    public static void Run(string workingDirectory, params string[] arguments)
    {
        var psi = new ProcessStartInfo("git")
        {
            WorkingDirectory = workingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        foreach (var argument in arguments)
            psi.ArgumentList.Add(argument);

        psi.Environment["GIT_AUTHOR_DATE"] = FixedDate;
        psi.Environment["GIT_COMMITTER_DATE"] = FixedDate;
        psi.Environment["GIT_AUTHOR_NAME"] = "Fixture";
        psi.Environment["GIT_AUTHOR_EMAIL"] = "fixture@example.invalid";
        psi.Environment["GIT_COMMITTER_NAME"] = "Fixture";
        psi.Environment["GIT_COMMITTER_EMAIL"] = "fixture@example.invalid";
        // A machine-wide hooks path or template dir would otherwise reach into these repos.
        psi.Environment["GIT_CONFIG_NOSYSTEM"] = "1";

        using var process = Process.Start(psi)!;
        var stdout = process.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();

        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException(
                $"git {string.Join(' ', arguments)} failed in {workingDirectory} " +
                $"(exit {process.ExitCode}): {stderr}{stdout}");
        }
    }

    /// <summary>Creates an empty repository with a commit, so HEAD exists.</summary>
    public static void InitWithRoot(string path)
    {
        Directory.CreateDirectory(path);
        Run(path, "init", "-q", "-b", "main");
        Run(path, "commit", "-q", "--allow-empty", "-m", "root");
    }
}
