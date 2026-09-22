namespace Synapse.Generator.Scanning;

/// <summary>
/// Scans the local filesystem for vault notes, skipping hidden directories (dotfiles, .obsidian, .git, etc.).
/// </summary>
public class FileSystemVaultScanner : IVaultScanner
{
    /// <inheritdoc />
    public IReadOnlyList<string> GetNoteFiles(string vaultRoot)
    {
        return Directory
            .EnumerateFiles(vaultRoot, "*.md", SearchOption.AllDirectories)
            .Where(f => !IsInHiddenPath(f, vaultRoot))
            .ToList();
    }

    /// <summary>
    /// Returns true if any path segment (directory component or the filename itself) starts with a dot.
    /// This skips .obsidian/, .git/, and any other hidden directories, as well as dotfiles.
    /// </summary>
    private static bool IsInHiddenPath(string absolutePath, string vaultRoot)
    {
        var relative = Path.GetRelativePath(vaultRoot, absolutePath);
        var segments = relative.Split(
            new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar },
            StringSplitOptions.RemoveEmptyEntries);

        return segments.Any(s => s.StartsWith('.'));
    }
}
