using System.Diagnostics;

namespace Synapse.Generator.Git;

/// <summary>
/// Shells out to <c>git log</c> to obtain a file's commit date history.
/// Dates are returned oldest-first (git log output is newest-first, so we reverse).
/// </summary>
public class GitHistoryReader : IGitHistoryReader
{
    /// <inheritdoc />
    public IReadOnlyList<string> GetHistory(string vaultRoot, string absoluteFilePath)
    {
        try
        {
            var relativePath = Path.GetRelativePath(vaultRoot, absoluteFilePath);

            var psi = new ProcessStartInfo("git")
            {
                WorkingDirectory = vaultRoot,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
            };

            // git log --follow --format=%ad --date=short -- <relativePath>
            psi.ArgumentList.Add("log");
            psi.ArgumentList.Add("--follow");
            psi.ArgumentList.Add("--format=%ad");
            psi.ArgumentList.Add("--date=short");
            psi.ArgumentList.Add("--");
            psi.ArgumentList.Add(relativePath);

            using var process = Process.Start(psi)!;
            var output = process.StandardOutput.ReadToEnd();
            process.WaitForExit();

            if (process.ExitCode != 0)
                return Array.Empty<string>();

            // git outputs newest-first; reverse to oldest-first.
            var dates = output
                .Split('\n', StringSplitOptions.RemoveEmptyEntries)
                .Select(d => d.Trim())
                .Where(d => d.Length > 0)
                .Reverse()
                .ToList();

            return dates;
        }
        catch
        {
            return Array.Empty<string>();
        }
    }
}
