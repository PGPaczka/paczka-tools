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

            // `--follow` is what carries a note's history across a rename, so it is tried
            // first. It also loses history entirely for a file that entered the repository
            // through `git subtree add --squash`: the squashed commit holds the content at
            // the subtree's own root while the mainline holds it under a prefix, and
            // rename detection gives up across that boundary — quietly, with exit code 0.
            // Any vault vendored into a larger repository looks like that, so an empty
            // answer is not taken as "no history" until a plain log has agreed.
            var followed = RunLog(vaultRoot, relativePath, follow: true);
            return followed.Count > 0
                ? followed
                : RunLog(vaultRoot, relativePath, follow: false);
        }
        catch
        {
            return Array.Empty<string>();
        }
    }

    private static IReadOnlyList<string> RunLog(string vaultRoot, string relativePath, bool follow)
    {
        var psi = new ProcessStartInfo("git")
        {
            WorkingDirectory = vaultRoot,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        // git log [--follow] --format=%ad --date=short -- <relativePath>
        psi.ArgumentList.Add("log");
        if (follow)
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
        return output
            .Split('\n', StringSplitOptions.RemoveEmptyEntries)
            .Select(d => d.Trim())
            .Where(d => d.Length > 0)
            .Reverse()
            .ToList();
    }
}
